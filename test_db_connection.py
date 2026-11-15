
import mariadb
import getpass

password = getpass.getpass("MariaDB root password: ")

try:
    connection = mariadb.connect(
        host="127.0.0.1",
        port=3306,
        user="root",
        password=password,
        database="wikiguardian",
    )

    cursor = connection.cursor()
    cursor.execute("SELECT DATABASE(), VERSION()")
    result = cursor.fetchone()

    print("Connection successful!")
    print("Database:", result[0])
    print("MariaDB version:", result[1])

    cursor.close()
    connection.close()

except mariadb.Error as error:
    print("Connection failed:", error)
