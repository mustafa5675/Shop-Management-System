"""
Database.py
===========
Single source of truth for MySQL connections.

Key fix over original:
  - cursorclass=DictCursor so every fetchone()/fetchall() returns a dict,
    which is what the rest of the code expects (e.g. row["column_name"]).
  - charset explicitly set to utf8mb4 to handle all Unicode characters.
  - autocommit=False: every operation must explicitly commit or rollback.
"""

import pymysql
import pymysql.cursors


def get_connection() -> pymysql.connections.Connection:
    return pymysql.connect(
        host       = "localhost",
        user       = "root",
        password   = "hello",          # change per environment
        database   = "Shop_Management",
        cursorclass= pymysql.cursors.DictCursor,
        charset    = "utf8mb4",
        autocommit = False
    )
