import pymysql
def get_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="hello",
        database="Shop_Management"
    )
