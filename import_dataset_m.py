"""Import MariaDB Wikipedia Dataset M (Finnish revision history) into the
system-versioned article_history table of the WikiGuardian database.

Dataset M holds every saved version of each "History of Finland" Finnish
article (862,076 versions). Loading all of it is ~5-7 GB in MariaDB, so this
script loads a chosen SUBSET, which is all a demo needs. Pick articles by id,
by title, or just take the first few:

    python import_dataset_m.py --titles "Suomen historia,Talvisota"   # by title
    python import_dataset_m.py --pages 29,1234                         # by page id
    python import_dataset_m.py --limit 30                             # first 30 articles

How the real edit times are preserved: MariaDB normally stamps each row with the
moment it is written. With  SET system_versioning_insert_history = 1  it accepts
row_start and row_end from us, so each version is stored with the time it was
saved on Wikipedia, and ends when the next version was saved. The newest version
is inserted with no row_end, so it stays current.

Requires migration 006 (the article_history table) to be applied first.
Safe to re-run: articles already present are skipped.
"""

import argparse
import getpass
import os
from datetime import datetime, timezone, timedelta
from pathlib import Path

import mariadb
import pyarrow as pa
import pyarrow.parquet as pq
import pyarrow.compute as pc
from dotenv import load_dotenv


ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "mariadb-wikipedia-datasets" / "data" / "m"
CHUNK = 50  # history rows per insert batch: small enough to bound client memory

COLUMNS = [
    "page_id", "title", "rev_id", "parent_id", "timestamp",
    "user", "anonymous", "comment", "minor", "sha1", "bytes", "text",
]


def connect():
    """Open a WikiGuardian connection, mirroring app.services.database_service."""

    load_dotenv(dotenv_path=ROOT / ".env", override=True, encoding="utf-8-sig")

    password = os.getenv("DB_PASSWORD") or getpass.getpass("MariaDB password: ")

    connection = mariadb.connect(
        host=os.getenv("DB_HOST", "127.0.0.1"),
        port=int(os.getenv("DB_PORT", "3306")),
        user=os.getenv("DB_USER", "root"),
        password=password,
        database=os.getenv("DB_NAME", "wikiguardian"),
        autocommit=False,
    )

    cursor = connection.cursor()
    cursor.execute("SET time_zone = '+00:00'")                 # Wikipedia's times are UTC
    cursor.execute("SET system_versioning_insert_history = 1")  # accept our row_start/row_end
    cursor.close()

    return connection


def parquet_files():
    files = sorted(DATA_DIR.glob("versions-*.parquet"))
    if not files:
        raise FileNotFoundError(f"No Dataset M parquet files in {DATA_DIR}")
    return files


def build_page_index(files):
    """Map every page_id to the file that holds its versions (pages do not split
    across files), plus a (page_id, title) list for title search."""

    page_to_file = {}
    titles = []

    for path in files:
        table = pq.read_table(path, columns=["page_id", "title"])
        page_ids = table.column("page_id").to_pylist()
        page_titles = table.column("title").to_pylist()

        for page_id, title in zip(page_ids, page_titles):
            if page_id not in page_to_file:
                page_to_file[page_id] = path
                titles.append((page_id, title))

    return page_to_file, titles


def resolve_wanted(args, page_to_file, titles):
    """Turn --pages / --titles / --limit into the set of page_ids to load."""

    if args.pages:
        wanted = {int(p) for p in args.pages.split(",") if p.strip()}
        missing = wanted - page_to_file.keys()
        if missing:
            print(f"  Warning: page_ids not found in Dataset M: {sorted(missing)}")
        wanted &= page_to_file.keys()

    elif args.titles:
        terms = [t.strip().lower() for t in args.titles.split(",") if t.strip()]
        wanted = {
            page_id
            for page_id, title in titles
            if title and any(term in title.lower() for term in terms)
        }

    else:
        # First N distinct articles, in file order.
        wanted = {page_id for page_id, _ in titles}

    ordered = [pid for pid, _ in titles if pid in wanted]

    if args.limit is not None:
        ordered = ordered[: args.limit]

    return ordered


def naive_utc(value):
    """pyarrow gives tz-aware UTC datetimes; store them naive in UTC."""

    if value is None:
        return None
    if isinstance(value, datetime) and value.tzinfo is not None:
        return value.astimezone(timezone.utc).replace(tzinfo=None)
    return value


def save(cursor, connection, page_id, versions):
    """Write all versions of one article: earlier ones as history rows (each
    ending when the next begins), the newest as the current row."""

    versions.sort(key=lambda v: (v["time"], v["rev_id"]))

    # Two edits in the same millisecond: keep order, nudge 1 microsecond apart.
    for i in range(1, len(versions)):
        if versions[i]["time"] <= versions[i - 1]["time"]:
            versions[i]["time"] = versions[i - 1]["time"] + timedelta(microseconds=1)

    rows = [
        (
            page_id, v["title"], v["rev_id"], v["parent_id"], v["user"],
            v["anonymous"], v["comment"], v["minor"], v["sha1"], v["bytes"],
            v["text"], v["time"],
        )
        for v in versions
    ]

    # Each historical version ends when the next one starts.
    history = [row + (versions[i + 1]["time"],) for i, row in enumerate(rows[:-1])]

    insert_history = """
        INSERT INTO article_history (
            page_id, title, rev_id, parent_id, editor, anonymous,
            comment, minor, sha1, bytes, text, row_start, row_end
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """

    # Insert in small batches. One giant executemany accumulates every parameter
    # set in client memory and overflows on long histories of large wikitext
    # ("Client run out of memory"); CHUNK rows at a time stays bounded and is far
    # faster than one row at a time.
    for start in range(0, len(history), CHUNK):
        cursor.executemany(insert_history, history[start:start + CHUNK])
        connection.commit()

    # The current version: no row_end, so it stays current.
    cursor.execute(
        """
        INSERT INTO article_history (
            page_id, title, rev_id, parent_id, editor, anonymous,
            comment, minor, sha1, bytes, text, row_start
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        rows[-1],
    )

    connection.commit()


def load_versions(cursor, connection, path, wanted, already):
    """Load all wanted articles whose versions live in one parquet file."""

    table = pq.read_table(path, columns=COLUMNS)

    target = [p for p in wanted if p not in already]
    if not target:
        return 0, 0

    value_set = pa.array(target, type=table.column("page_id").type)
    mask = pc.is_in(table.column("page_id"), value_set=value_set)
    table = table.filter(mask)

    by_page = {}
    for record in table.to_pylist():
        by_page.setdefault(record["page_id"], []).append(record)

    pages_done = versions_done = 0

    for page_id, records in by_page.items():
        versions = [
            {
                "title": r["title"],
                "rev_id": r["rev_id"],
                "parent_id": r["parent_id"],
                "user": r["user"],
                "anonymous": bool(r["anonymous"]),
                "comment": r["comment"],
                "minor": bool(r["minor"]),
                "sha1": r["sha1"],
                "bytes": r["bytes"],
                "text": r["text"] or "",
                "time": naive_utc(r["timestamp"]),
            }
            for r in records
        ]

        save(cursor, connection, page_id, versions)
        already.add(page_id)
        pages_done += 1
        versions_done += len(versions)
        print(f"  {versions[0]['title']}: {len(versions)} versions", flush=True)

    return pages_done, versions_done


def verify(cursor):
    """Prove system versioning works: counts, then one point-in-time read."""

    cursor.execute(
        "SELECT COUNT(DISTINCT page_id), COUNT(*) FROM article_history FOR SYSTEM_TIME ALL"
    )
    articles, rows = cursor.fetchone()
    print(f"\nIn article_history: {articles} articles, {rows} versions (all history).")

    cursor.execute(
        """
        SELECT page_id, title, MIN(row_start)
        FROM article_history FOR SYSTEM_TIME ALL
        GROUP BY page_id, title
        ORDER BY MIN(row_start)
        LIMIT 1
        """
    )
    sample = cursor.fetchone()
    if not sample:
        return

    page_id, title, first_seen = sample
    print(f"\nPoint-in-time check for page {page_id} ({title!r}):")

    cursor.execute(
        """
        SELECT title, bytes, row_start
        FROM article_history FOR SYSTEM_TIME AS OF ?
        WHERE page_id = ?
        """,
        (first_seen, page_id),
    )
    as_of = cursor.fetchone()
    if as_of:
        print(f"  AS OF {first_seen}: title={as_of[0]!r}, {as_of[1]} bytes")

    cursor.execute(
        "SELECT title, bytes FROM article_history WHERE page_id = ?",
        (page_id,),
    )
    current = cursor.fetchone()
    if current:
        print(f"  NOW:            title={current[0]!r}, {current[1]} bytes")


def main():
    parser = argparse.ArgumentParser(
        description="Import a subset of Dataset M into article_history (SVT)."
    )
    parser.add_argument("--pages", help="Comma-separated Wikipedia page_ids.")
    parser.add_argument("--titles", help="Comma-separated title substrings (case-insensitive).")
    parser.add_argument("--limit", type=int, help="Maximum number of articles to load.")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Drop and recreate article_history before loading (clears any partial load).",
    )
    args = parser.parse_args()

    files = parquet_files()

    print("Indexing Dataset M (page ids and titles)...")
    page_to_file, titles = build_page_index(files)
    print(f"  {len(page_to_file)} articles across {len(files)} files.")

    wanted = resolve_wanted(args, page_to_file, titles)

    if not wanted:
        raise SystemExit(
            "No articles selected. Use --pages, --titles, or --limit."
        )

    print(f"Selected {len(wanted)} article(s) to load.")

    connection = connect()
    cursor = connection.cursor()

    try:
        if args.reset:
            print("Resetting article_history (drop + recreate)...")
            cursor.execute("DROP TABLE IF EXISTS article_history")
            connection.commit()
            ddl = (ROOT / "migrations" / "006_article_history_svt.sql").read_text(
                encoding="utf-8"
            )
            # Strip comment lines; the file holds a single CREATE statement.
            ddl = "\n".join(
                line for line in ddl.splitlines() if not line.strip().startswith("--")
            )
            cursor.execute(ddl)
            connection.commit()

        cursor.execute("SELECT DISTINCT page_id FROM article_history FOR SYSTEM_TIME ALL")
        already = {row[0] for row in cursor.fetchall()}

        # Group wanted pages by the file that holds them.
        by_file = {}
        for page_id in wanted:
            by_file.setdefault(page_to_file[page_id], []).append(page_id)

        total_pages = total_versions = 0

        for path, pages in by_file.items():
            print(f"\nReading {path.name} ({len(pages)} article(s))...")
            pages_done, versions_done = load_versions(
                cursor, connection, path, pages, already
            )
            total_pages += pages_done
            total_versions += versions_done

        print(f"\nImport complete: {total_pages} new article(s), {total_versions} versions.")

        verify(cursor)

    except Exception:
        connection.rollback()
        print("\nImport failed. The current transaction was rolled back.")
        raise

    finally:
        cursor.close()
        connection.close()


if __name__ == "__main__":
    main()
