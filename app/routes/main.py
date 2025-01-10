from flask import Blueprint, render_template
from flask_login import current_user
from app.database.connection import get_db
from app.utils.elo import getElo
from app.utils.helpers import format_name
import json
from datetime import datetime
import logging

bp = Blueprint('main', __name__)

def load_league_data():
    """Función única para cargar todos los datos necesarios"""
    conn = get_db()
    cur = conn.cursor()
    
    # Definir la fecha de inicio de las penalizaciones (2025/01/13)
    start_date = datetime(2025, 1, 13)
    
    try:
        # Asegurarse de que todos los jugadores en la base de datos estén en start.json
        cur.execute('SELECT name, initial_rating FROM players')
        db_players = {row['name']: row['initial_rating'] for row in cur.fetchall()}
        
        with open('start.json', 'r', encoding='utf-8') as f:
            start_data = json.load(f)
            
        # Verificar si hay jugadores en la base de datos que no están en start.json
        start_players = {p['name']: p['rating'] for p in start_data['players']}
        for name, rating in db_players.items():
            if name not in start_players:
                # Agregar jugador faltante a start.json
                start_data['players'].append({
                    'name': name,
                    'rating': rating
                })
                
        # Guardar cambios en start.json si hubo modificaciones
        if len(start_players) != len(db_players):
            with open('start.json', 'w', encoding='utf-8') as f:
                json.dump(start_data, f, indent=4, ensure_ascii=False)
        
        # Una sola consulta para juegos con ratings históricos
        cur.execute('''
            WITH weekly_counts AS (
                SELECT player, COUNT(*) as games_this_week
                FROM (
                    SELECT white as player FROM games 
                    WHERE date >= %s
                      AND date >= NOW() - INTERVAL '7 days'
                    UNION ALL
                    SELECT black FROM games 
                    WHERE date >= %s
                      AND date >= NOW() - INTERVAL '7 days'
                ) w
                GROUP BY player
            )
            SELECT 
                g.white, g.black, g.result, g.date,
                g.has_lettuce_factor,
                CASE 
                    WHEN NOW() >= %s THEN COALESCE(w1.games_this_week, 0)
                    ELSE 3
                END as white_weekly_games,
                CASE 
                    WHEN NOW() >= %s THEN COALESCE(w2.games_this_week, 0)
                    ELSE 3
                END as black_weekly_games
            FROM games g
            LEFT JOIN weekly_counts w1 ON g.white = w1.player
            LEFT JOIN weekly_counts w2 ON g.black = w2.player
            ORDER BY g.date DESC
        ''', (start_date, start_date, start_date, start_date))
        games = [dict(row) for row in cur.fetchall()]
        
        # Una consulta para todos los jugadores y sus conteos
        cur.execute('''
            SELECT 
                p.id,
                p.name,
                CASE 
                    WHEN NOW() >= %s THEN COALESCE(w.games_this_week, 0)
                    ELSE 3
                END as games_this_week
            FROM players p
            LEFT JOIN (
                SELECT player, COUNT(*) as games_this_week
                FROM (
                    SELECT white as player FROM games 
                    WHERE date >= %s
                      AND date >= NOW() - INTERVAL '7 days'
                    UNION ALL
                    SELECT black FROM games 
                    WHERE date >= %s
                      AND date >= NOW() - INTERVAL '7 days'
                ) w
                GROUP BY player
            ) w ON p.name = w.player
        ''', (start_date, start_date, start_date))
        players = [dict(row) for row in cur.fetchall()]
        
    except Exception as e:
        logging.error(f"Error cargando datos de la liga: {str(e)}")
        games = []
        players = []
        
    finally:
        cur.close()
        conn.close()
    
    return games, players

@bp.route('/')
def index():
    games, players_data = load_league_data()
    
    # Calcular ratings (en memoria)
    with open('start.json', 'r', encoding='utf-8') as f:
        start_data = json.load(f)
        current_ratings = {p['name']: p['rating'] for p in start_data['players']}
    
    # Ordenar juegos por fecha (más antiguo primero)
    games.sort(key=lambda x: x['date'])
    
    # Procesar juegos y calcular cambios
    processed_games = []
    historical_ratings = current_ratings.copy()  # Mantener una copia de los ratings históricos
    
    for game in games:
        # Verificar que ambos jugadores existan en current_ratings
        if game['white'] not in historical_ratings or game['black'] not in historical_ratings:
            logging.error(f"Jugador no encontrado en ratings: {game['white']} o {game['black']}")
            continue
            
        white_rating = historical_ratings[game['white']]
        black_rating = historical_ratings[game['black']]
        
        new_white, new_black = getElo(white_rating, black_rating, 50, game['result'])
        white_change = new_white - white_rating
        black_change = new_black - black_rating
        
        processed_games.append({
            **game,
            'white_display': format_name(game['white']),
            'black_display': format_name(game['black']),
            'white_rating': white_rating,  # Rating antes del juego
            'black_rating': black_rating,  # Rating antes del juego
            'white_change': white_change,
            'black_change': black_change,
            'date': game['date'].strftime('%Y-%m-%d %H:%M:%S')
        })
        
        # Actualizar ratings históricos para el siguiente juego
        historical_ratings[game['white']] = new_white
        historical_ratings[game['black']] = new_black
    
    # Revertir el orden para mostrar los más recientes primero
    processed_games.reverse()
    
    # Preparar datos de jugadores usando los ratings finales (históricos)
    players = []
    for p in players_data:
        # Verificar que el jugador exista en historical_ratings
        if p['name'] not in historical_ratings:
            logging.error(f"Jugador no encontrado en ratings: {p['name']}")
            continue
            
        players.append({
            'id': p['id'],
            'name': p['name'],
            'display_name': format_name(p['name']),
            'rating': historical_ratings[p['name']],  # Usar el rating final después de todos los juegos
            'games_this_week': p['games_this_week'],
            'warning': p['games_this_week'] < 3
        })
    
    players.sort(key=lambda x: x['rating'], reverse=True)
    
    # Obtener el player_id del usuario actual si está logueado
    current_player_id = None
    if current_user.is_authenticated and current_user.player_name:
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT id FROM players WHERE name = %s', (current_user.player_name,))
        result = cur.fetchone()
        if result:
            current_player_id = result['id']
        cur.close()
        conn.close()
    
    return render_template('index.html',
                         players=players,
                         games=processed_games,
                         is_admin=current_user.is_admin if not current_user.is_anonymous else False,
                         current_player_id=current_player_id) 