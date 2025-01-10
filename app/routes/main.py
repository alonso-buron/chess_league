from flask import Blueprint, render_template
from flask_login import current_user
from app.database.connection import get_db
from app.utils.elo import getElo
from app.utils.helpers import format_name
import json
from datetime import datetime
from flask import current_app
import sys

bp = Blueprint('main', __name__)

def debug_print(message):
    print(message, file=sys.stdout, flush=True)
    sys.stdout.flush()

@bp.route('/')
def index():
    debug_print("\n\n=== INICIO DE PROCESAMIENTO ===")
    
    conn = get_db()
    cur = conn.cursor()
    
    # Obtener todos los juegos
    cur.execute('''
        SELECT g.*, 
               w.name as white_name, w.display_name as white_display,
               b.name as black_name, b.display_name as black_display,
               g.created_at::timestamp::date as game_date
        FROM games g
        JOIN players w ON g.white_player_id = w.id
        JOIN players b ON g.black_player_id = b.id
        ORDER BY g.created_at DESC;
    ''')
    
    games = cur.fetchall()
    debug_print(f"Número de juegos encontrados: {len(games)}")
    if games:
        debug_print(f"Primer juego como ejemplo: {dict(games[0])}")
    
    # Obtener todos los jugadores
    cur.execute('''
        SELECT p.*, COALESCE(wg.games_count, 0) as games_this_week,
               CASE WHEN COALESCE(wg.games_count, 0) < 3 THEN true ELSE false END as warning
        FROM players p
        LEFT JOIN (
            SELECT player_id, COUNT(*) as games_count
            FROM (
                SELECT white_player_id as player_id FROM games 
                WHERE created_at >= NOW() - INTERVAL '7 days'
                UNION ALL
                SELECT black_player_id FROM games 
                WHERE created_at >= NOW() - INTERVAL '7 days'
            ) as all_games
            GROUP BY player_id
        ) wg ON p.id = wg.player_id
    ''')
    
    players_data = cur.fetchall()
    print(f"Número de jugadores encontrados: {len(players_data)}", flush=True)
    
    # Calcular ratings (en memoria)
    with open('start.json', 'r', encoding='utf-8') as f:
        start_data = json.load(f)
        current_ratings = {p['name']: p['rating'] for p in start_data['players']}
    
    # Ordenar juegos por fecha (más antiguo primero)
    games.sort(key=lambda x: x['date'])
    
    # Procesar juegos y calcular cambios
    processed_games = []
    historical_ratings = current_ratings.copy()
    player_stats = {}
    print("\n\n=== INICIO DE PROCESAMIENTO ===")
    print(f"Número de juegos: {len(games)}")
    print(f"Número de jugadores: {len(players_data)}")
    
    for game in games:
        print(f"\nProcesando juego: {game['white_name']} vs {game['black_name']} - Resultado: {game['result']}")
        
        # Verificar que ambos jugadores existan en current_ratings
        if game['white_name'] not in historical_ratings or game['black_name'] not in historical_ratings:
            logger.error(f"Jugador no encontrado en ratings: {game['white_name']} o {game['black_name']}")
            continue
            
        # Inicializar estadísticas si no existen
        if game['white_name'] not in player_stats:
            player_stats[game['white_name']] = {'white_games': 0, 'white_wins': 0, 'white_draws': 0,
                                         'black_games': 0, 'black_wins': 0, 'black_draws': 0}
        if game['black_name'] not in player_stats:
            player_stats[game['black_name']] = {'white_games': 0, 'white_wins': 0, 'white_draws': 0,
                                         'black_games': 0, 'black_wins': 0, 'black_draws': 0}
        
        # Actualizar juegos de blancas
        stats_white = player_stats[game['white_name']]
        stats_white['white_games'] += 1
        if game['result'] == '1.0':
            stats_white['white_wins'] += 1
        elif game['result'] == '0.5':
            stats_white['white_draws'] += 1
        
        # Actualizar juegos de negras
        stats_black = player_stats[game['black_name']]
        stats_black['black_games'] += 1
        if game['result'] == '0.0':
            stats_black['black_wins'] += 1
        elif game['result'] == '0.5':
            stats_black['black_draws'] += 1
        
        print(f"Stats actualizadas:")
        print(f"- {game['white_name']}: {stats_white}")
        print(f"- {game['black_name']}: {stats_black}")
        
        white_rating = historical_ratings[game['white_name']]
        black_rating = historical_ratings[game['black_name']]
        
        new_white, new_black = getElo(white_rating, black_rating, 50, game['result'])
        white_change = new_white - white_rating
        black_change = new_black - black_rating
        
        processed_games.append({
            **game,
            'white_display': game['white_display'],
            'black_display': game['black_display'],
            'white_rating': white_rating,  # Rating antes del juego
            'black_rating': black_rating,  # Rating antes del juego
            'white_change': white_change,
            'black_change': black_change,
            'date': game['date'].strftime('%Y-%m-%d %H:%M:%S')
        })
        
        # Actualizar ratings históricos para el siguiente juego
        historical_ratings[game['white_name']] = new_white
        historical_ratings[game['black_name']] = new_black
    
    # Revertir el orden para mostrar los más recientes primero
    processed_games.reverse()
    
    print("\n=== ESTADÍSTICAS FINALES ===")
    for name, stats in player_stats.items():
        print(f"{name}: {stats}")
    print("\n=== CREANDO DICCIONARIOS DE JUGADORES ===")
    
    # Preparar datos de jugadores
    players = []
    for p in players_data:
        print(f"\nProcesando jugador: {p['name']}")
        
        stats = player_stats.get(p['name'], {'white_games': 0, 'white_wins': 0, 'white_draws': 0,
                                            'black_games': 0, 'black_wins': 0, 'black_draws': 0})
        
        white_winrate = 0 if stats['white_games'] == 0 else \
            round((stats['white_wins'] + stats['white_draws'] * 0.5) / stats['white_games'] * 100, 1)
        
        black_winrate = 0 if stats['black_games'] == 0 else \
            round((stats['black_wins'] + stats['black_draws'] * 0.5) / stats['black_games'] * 100, 1)
        
        print(f"Stats: {stats}")
        print(f"Winrates calculados - Blancas: {white_winrate}%, Negras: {black_winrate}%")
        
        player_dict = {
            'id': p['id'],
            'name': p['name'],
            'display_name': p['display_name'],
            'rating': historical_ratings[p['name']],
            'games_this_week': p['games_this_week'],
            'white_winrate': white_winrate,
            'black_winrate': black_winrate,
            'white_games': stats['white_games'],
            'black_games': stats['black_games'],
            'warning': p['warning']
        }
        print(f"Diccionario creado: {player_dict}")
        players.append(player_dict)
    
    players.sort(key=lambda x: x['rating'], reverse=True)
    
    # Debug: imprimir datos para verificar
    if players and player_stats:
        logger.info(f"Primer jugador: {players[0]}")
        logger.info(f"Stats del primer jugador: {player_stats.get(players[0]['name'], 'No encontrado')}")
    
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
    
    logger.info("Finalizó procesamiento de juegos. Estado de player_stats:")
    for player_name, stats in player_stats.items():
        logger.info(f"{player_name}: {stats}")
    
    return render_template('index.html',
                         players=players,
                         games=processed_games,
                         player_stats=player_stats,
                         is_admin=current_user.is_admin if not current_user.is_anonymous else False,
                         current_player_id=current_player_id) 

def get_players():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('''
            WITH weekly_games AS (
                SELECT player_id, COUNT(*) as games_count
                FROM (
                    SELECT white_player_id as player_id FROM games 
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                    UNION ALL
                    SELECT black_player_id FROM games 
                    WHERE created_at >= NOW() - INTERVAL '7 days'
                ) as all_games
                GROUP BY player_id
            )
            SELECT 
                p.id,
                p.name,
                p.display_name,
                p.rating,
                COALESCE(wg.games_count, 0) as games_this_week,
                CASE WHEN COALESCE(wg.games_count, 0) < 3 THEN true ELSE false END as warning
            FROM players p
            LEFT JOIN weekly_games wg ON p.id = wg.player_id
            ORDER BY p.rating DESC;
        ''')
        
        players = []
        for row in cur.fetchall():
            players.append({
                'id': row['id'],
                'name': row['name'],
                'display_name': row['display_name'],
                'rating': row['rating'],
                'games_this_week': row['games_this_week'],
                'warning': row['warning']
            })
        
        return players
    except Exception as e:
        logging.error(f"Error cargando datos de los jugadores: {str(e)}")
        return [] 

@bp.route('/debug_logs')
def view_logs():
    try:
        with open('debug.log', 'r') as f:
            logs = f.read()
        return f'<pre>{logs}</pre>'
    except FileNotFoundError:
        return 'No hay logs disponibles' 