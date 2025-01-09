import psycopg2
from psycopg2.extras import DictCursor
import json
import os
from dotenv import load_dotenv

# Cargar variables de entorno desde .env
load_dotenv()

def init_players():
    # Cargar jugadores desde start.json
    with open('start.json', 'r', encoding='utf-8') as f:
        start_data = json.load(f)
    
    conn = psycopg2.connect(os.environ.get('POSTGRES_URL'))
    cur = conn.cursor()
    
    # Crear tabla si no existe
    cur.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            initial_rating INTEGER NOT NULL
        )
    ''')
    
    for player in start_data['players']:
        cur.execute(
            '''
            INSERT INTO players (name, initial_rating) 
            VALUES (%s, %s)
            ON CONFLICT (name) DO NOTHING
            ''',
            (player['name'], player['rating'])
        )
    
    conn.commit()
    cur.close()
    conn.close()

if __name__ == '__main__':
    init_players() 