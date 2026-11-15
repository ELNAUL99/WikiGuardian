from pathlib import Path
import pyarrow.parquet as pq

DATA_DIR = (
    Path(__file__).parent
    / "mariadb-wikipedia-datasets"
    / "data"
    / "s"
)

files = sorted(DATA_DIR.glob("*.parquet"))

if not files:
    raise FileNotFoundError(f"No Parquet files found in {DATA_DIR}")

for path in files:
    print("\n" + "=" * 70)
    print(f"FILE: {path.name}")

    parquet = pq.ParquetFile(path)

    print(f"ROWS: {parquet.metadata.num_rows:,}")
    print(f"ROW GROUPS: {parquet.metadata.num_row_groups}")
    print("SCHEMA:")
    print(parquet.schema_arrow)

    sample = parquet.read_row_group(0).slice(0, 1).to_pylist()[0]

    print("FIRST RECORD:")
    for column, value in sample.items():
        if column == "embedding" and value is not None:
            print(f"  {column}: vector with {len(value)} dimensions")
            print(f"  First 5 values: {value[:5]}")
        elif isinstance(value, str) and len(value) > 300:
            print(f"  {column}: {value[:300]}...")
        else:
            print(f"  {column}: {value!r}")

print("\nInspection completed.")
