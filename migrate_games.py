import json
import psycopg2
from psycopg2.extras import DictCursor
import os
from dotenv import load_dotenv
from datetime import datetime

# Cargar variables de entorno
load_dotenv()

def migrate_games():
    # Cargar juegos desde league.json
    with open('league.json', 'r', encoding='utf-8') as f:
        league_data = json.load(f)
    
    # Conectar a la base de datos
    conn = psycopg2.connect(os.environ.get('POSTGRES_URL'))
    cur = conn.cursor()
    
    try:
        # Obtener el ID del admin
        cur.execute('SELECT id FROM users WHERE username = %s', ('admin',))
        admin_id = cur.fetchone()[0]
        
        # Limpiar juegos existentes
        cur.execute('TRUNCATE TABLE games')
        
        # Insertar cada juego
        for game in league_data['games']:
            cur.execute(
                '''
                INSERT INTO games (white, black, result, date, added_by) 
                VALUES (%s, %s, %s, %s, %s)
                ''',
                (
                    game['white'],
                    game['black'],
                    float(game['result']),
                    datetime.strptime(game['date'], '%Y-%m-%d %H:%M:%S'),
                    admin_id
                )
            )
        
        conn.commit()
        print(f"Migrados {len(league_data['games'])} juegos exitosamente")
        
    except Exception as e:
        conn.rollback()
        print(f"Error durante la migración: {str(e)}")
        raise e
    finally:
        cur.close()
        conn.close()

if __name__ == '__main__':
    migrate_games() 