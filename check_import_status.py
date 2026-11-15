
import mariadb
import getpass

password = getpass.getpass("MariaDB root password: ")

connection = mariadb.connect(
    host="127.0.0.1",
    port=3306,
    user="root",
    password=password,
    database="wikiguardian",
)

cursor = connection.cursor()

tables = [
    "articles",
    "article_revisions",
    "article_chunks",
    "chunk_embeddings",
]

for table in tables:
    cursor.execute(f"SELECT COUNT(*) FROM `{table}`")
    count = cursor.fetchone()[0]
    print(f"{table}: {count}")

cursor.close()
connection.close()
