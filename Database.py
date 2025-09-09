import pymysql

def get_connection():
    return pymysql.connect(
        host="localhost",
        user="root",
        password="hello",   # use env var later
        database="Shop_Management",
        cursorclass=pymysql.cursors.DictCursor  # return dict rows
    )
