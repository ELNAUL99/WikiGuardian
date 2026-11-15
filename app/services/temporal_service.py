"""Read-layer for Wikipedia's revision history in the system-versioned
article_history table (MariaDB Dataset M).

These are the "Wikipedia through time" queries the verifier and UI build on:

    * get_content_as_of(page_id, when)  - what the article said at a point in time
    * get_revision_timeline(page_id)    - every version, with its validity window
    * get_change_signals(page_id)       - edit count, reverts, edit-war / churn signals

article_history is keyed by Wikipedia page_id, which equals
articles.wikipedia_page_id; resolve_page_id() maps an app article_id to it.
History is Finnish-only (Dataset M is fi), so these return None / empty for
articles with no loaded history.
"""

from datetime import datetime, timezone

from app.services.database_service import get_database_connection


# MariaDB stores the current row's end bound as the maximum TIMESTAMP value.
_CURRENT_ROW_END_YEAR = 2038


def _row_is_current(row_end) -> bool:
    year = getattr(row_end, "year", None)
    return year is not None and year >= _CURRENT_ROW_END_YEAR


def _to_param(when):
    """Accept a datetime or ISO string for FOR SYSTEM_TIME AS OF."""

    if isinstance(when, datetime):
        if when.tzinfo is not None:
            when = when.astimezone(timezone.utc).replace(tzinfo=None)
        return when
    return str(when)


def resolve_page_id(article_id: int, connection=None):
    """Map an app article_id to its Wikipedia page_id (article_history key).

    Pass an open connection to reuse it (it is not closed); otherwise one is
    opened and closed here.
    """

    if not isinstance(article_id, int) or article_id <= 0:
        raise ValueError("A valid article ID is required.")

    owns = connection is None
    connection = connection or get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            "SELECT wikipedia_page_id FROM articles WHERE article_id = ?",
            (article_id,),
        )
        row = cursor.fetchone()
        return int(row[0]) if row else None
    finally:
        cursor.close()
        if owns:
            connection.close()


def has_history(page_id: int) -> bool:
    """Whether any revision history is loaded for this page."""

    if not isinstance(page_id, int) or page_id <= 0:
        raise ValueError("A valid page ID is required.")

    connection = get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT 1 FROM article_history FOR SYSTEM_TIME ALL
            WHERE page_id = ? LIMIT 1
            """,
            (page_id,),
        )
        return cursor.fetchone() is not None
    finally:
        cursor.close()
        connection.close()


def get_content_as_of(page_id: int, when, connection=None):
    """Return the version of an article that was current at `when`.

    `when` is a datetime or ISO timestamp string. Returns None if the article
    did not exist yet at that time (or has no loaded history). Pass an open
    connection to reuse it (it is not closed); otherwise one is opened here.
    """

    if not isinstance(page_id, int) or page_id <= 0:
        raise ValueError("A valid page ID is required.")

    owns = connection is None
    connection = connection or get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT title, rev_id, editor, anonymous, comment, minor,
                   sha1, bytes, text, row_start
            FROM article_history FOR SYSTEM_TIME AS OF ?
            WHERE page_id = ?
            """,
            (_to_param(when), page_id),
        )
        row = cursor.fetchone()

        if row is None:
            return None

        return {
            "page_id": page_id,
            "title": row[0],
            "rev_id": row[1],
            "editor": row[2],
            "anonymous": bool(row[3]),
            "comment": row[4],
            "minor": bool(row[5]),
            "sha1": row[6],
            "bytes": row[7],
            "text": row[8],
            "valid_from": row[9],
        }
    finally:
        cursor.close()
        if owns:
            connection.close()


def get_revision_timeline(page_id: int, limit: int | None = None, connection=None):
    """Return every version of an article, oldest first, without the text body.

    Each entry carries its validity window (valid_from / valid_to) and whether
    it is the current version, read from the system-versioned history. Pass an
    open connection to reuse it (it is not closed); otherwise one is opened here.
    """

    if not isinstance(page_id, int) or page_id <= 0:
        raise ValueError("A valid page ID is required.")

    if limit is not None and (not isinstance(limit, int) or limit <= 0):
        raise ValueError("limit must be a positive integer.")

    owns = connection is None
    connection = connection or get_database_connection()
    cursor = connection.cursor()

    try:
        query = """
            SELECT rev_id, parent_id, editor, anonymous, comment, minor,
                   sha1, bytes, row_start, row_end
            FROM article_history FOR SYSTEM_TIME ALL
            WHERE page_id = ?
            ORDER BY row_start, rev_id
        """
        params = [page_id]

        if limit is not None:
            query += " LIMIT ?"
            params.append(limit)

        cursor.execute(query, tuple(params))

        return [
            {
                "rev_id": row[0],
                "parent_id": row[1],
                "editor": row[2],
                "anonymous": bool(row[3]),
                "comment": row[4],
                "minor": bool(row[5]),
                "sha1": row[6],
                "bytes": row[7],
                "valid_from": row[8],
                "valid_to": row[9],
                "is_current": _row_is_current(row[9]),
            }
            for row in cursor.fetchall()
        ]
    finally:
        cursor.close()
        if owns:
            connection.close()


def get_change_signals(page_id: int, connection=None):
    """Summarize how contested an article's history is.

    Computed from the full version history: edit volume, who edits, and reverts
    (a version whose text matches an earlier one but not the one just before it,
    identified by sha1 - the dataset's own revert definition). A high revert
    count flags likely edit wars / contested content for the verifier and UI.

    Pass an open connection to reuse it (it is not closed); otherwise one is
    opened and closed here.
    """

    if not isinstance(page_id, int) or page_id <= 0:
        raise ValueError("A valid page ID is required.")

    owns = connection is None
    connection = connection or get_database_connection()
    cursor = connection.cursor()

    try:
        cursor.execute(
            """
            SELECT title, editor, anonymous, minor, sha1, row_start
            FROM article_history FOR SYSTEM_TIME ALL
            WHERE page_id = ?
            ORDER BY row_start, rev_id
            """,
            (page_id,),
        )
        rows = cursor.fetchall()
    finally:
        cursor.close()
        if owns:
            connection.close()

    if not rows:
        return None

    title = rows[0][0]
    editors = set()
    anonymous_edits = 0
    minor_edits = 0
    reverts = 0

    seen_sha1 = set()
    previous_sha1 = None

    for _, editor, anonymous, minor, sha1, _row_start in rows:
        if editor:
            editors.add(editor)
        if anonymous:
            anonymous_edits += 1
        if minor:
            minor_edits += 1

        # Revert: matches an earlier version, but not the immediately prior one.
        if sha1 is not None and sha1 != previous_sha1 and sha1 in seen_sha1:
            reverts += 1

        seen_sha1.add(sha1)
        previous_sha1 = sha1

    first_edit = rows[0][5]
    last_edit = rows[-1][5]

    # Busiest calendar day, a simple churn proxy.
    by_day = {}
    for row in rows:
        row_start = row[5]
        day = row_start.date() if hasattr(row_start, "date") else None
        if day is not None:
            by_day[day] = by_day.get(day, 0) + 1
    busiest_day_edits = max(by_day.values()) if by_day else 0

    total = len(rows)

    # Heuristic: many reverts or a heavy single-day spike => likely contested.
    contested = reverts >= 3 or busiest_day_edits >= 10

    return {
        "page_id": page_id,
        "title": title,
        "total_versions": total,
        "first_edit": first_edit,
        "last_edit": last_edit,
        "distinct_editors": len(editors),
        "anonymous_edits": anonymous_edits,
        "minor_edits": minor_edits,
        "reverts": reverts,
        "busiest_day_edits": busiest_day_edits,
        "contested": contested,
    }


if __name__ == "__main__":
    # Quick manual check:  python -m app.services.temporal_service 1275
    import sys

    page = int(sys.argv[1]) if len(sys.argv) > 1 else 1275

    print(f"=== change signals for page {page} ===")
    signals = get_change_signals(page)
    if signals is None:
        print("No history loaded for this page.")
        raise SystemExit(0)

    for key, value in signals.items():
        print(f"  {key}: {value}")

    timeline = get_revision_timeline(page, limit=3)
    print(f"\n=== first {len(timeline)} versions ===")
    for item in timeline:
        print(f"  {item['valid_from']}  {item['bytes']} bytes  by {item['editor']}")

    first_seen = signals["first_edit"]
    snapshot = get_content_as_of(page, first_seen)
    current = get_content_as_of(page, datetime.now(timezone.utc))
    if snapshot and current:
        print("\n=== point-in-time ===")
        print(f"  AS OF {first_seen}: {snapshot['bytes']} bytes")
        print(f"  NOW:            {current['bytes']} bytes")
