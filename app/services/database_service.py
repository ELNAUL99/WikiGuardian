import getpass
import os
from pathlib import Path

import mariadb
from dotenv import load_dotenv


def get_database_connection():
    """Create and return a WikiGuardian MariaDB connection."""

    project_root = Path(__file__).resolve().parents[2]

    load_dotenv(
        dotenv_path=project_root / ".env",
        override=True,
        encoding="utf-8-sig",
    )

    password = os.getenv("DB_PASSWORD")

    if not password:
        password = getpass.getpass("MariaDB password: ")

    try:
        connection = mariadb.connect(
            host=os.getenv("DB_HOST", "127.0.0.1"),
            port=int(os.getenv("DB_PORT", "3306")),
            user=os.getenv("DB_USER", "root"),
            password=password,
            database=os.getenv("DB_NAME", "wikiguardian"),
            autocommit=False,
        )

        cursor = connection.cursor()

        try:
            cursor.execute("SET mhnsw_ef_search = 80")
        finally:
            cursor.close()

        return connection

    except mariadb.Error as exc:
        raise RuntimeError(
            f"Could not connect to WikiGuardian database: {exc}"
        ) from exc
