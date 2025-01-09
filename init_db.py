import psycopg2
from psycopg2.extras import DictCursor
import json
import os
from urllib.parse import urlparse

def init_players():
    # Cargar jugadores desde start.json
    with open('start.json', 'r', encoding='utf-8') as f:
        start_data = json.load(f)
    
    url = urlparse(os.environ.get('POSTGRES_URL'))
    conn = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
    )
    cur = conn.cursor()
    
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