import psycopg2
from psycopg2.extras import DictCursor
import os

def get_db():
    connection = psycopg2.connect(
        os.environ.get('POSTGRES_URL'),
        sslmode='require'
    )
    connection.cursor_factory = DictCursor
    return connection

def init_db():
    # Código actual de init_db... 