from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_from_directory
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from datetime import datetime, timedelta
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor
from werkzeug.security import generate_password_hash, check_password_hash
import json
from functools import wraps
import time
from werkzeug.middleware.proxy_fix import ProxyFix
import logging
import sys

# Configurar logging
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables de entorno desde .env en desarrollo
load_dotenv()

app = Flask(__name__)
app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database setup
def get_db():
    connection = psycopg2.connect(
        os.environ.get('POSTGRES_URL'),
        sslmode='require'
    )
    connection.cursor_factory = DictCursor
    return connection

def init_db():
    conn = get_db()
    cur = conn.cursor()
    
    # Crear tablas
    cur.execute('''
        CREATE TABLE IF NOT EXISTS users (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            is_admin BOOLEAN NOT NULL DEFAULT FALSE
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS games (
            id SERIAL PRIMARY KEY,
            white TEXT NOT NULL,
            black TEXT NOT NULL,
            result REAL NOT NULL,
            date TIMESTAMP NOT NULL
        )
    ''')
    
    cur.execute('''
        CREATE TABLE IF NOT EXISTS players (
            id SERIAL PRIMARY KEY,
            name TEXT UNIQUE NOT NULL,
            initial_rating INTEGER NOT NULL
        )
    ''')
    
    # Crear admin si no existe
    cur.execute(
        '''
        INSERT INTO users (username, password_hash, is_admin) 
        VALUES (%s, %s, %s)
        ON CONFLICT (username) DO NOTHING
        ''',
        ('admin', generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin')), True)
    )
    
    conn.commit()
    cur.close()
    conn.close()

class User(UserMixin):
    def __init__(self, id, username, is_admin):
        self.id = id
        self.username = username
        self.is_admin = is_admin

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT * FROM users WHERE id = %s', (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user:
        return User(user['id'], user['username'], user['is_admin'])
    return None

def load_league_data():
    """Función única para cargar todos los datos necesarios"""
    conn = get_db()
    cur = conn.cursor()
    
    # Definir la fecha de inicio de las penalizaciones (2025/01/13)
    start_date = datetime(2025, 1, 13)
    
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
            CASE 
                WHEN NOW() >= %s THEN COALESCE(w1.games_this_week, 0)
                ELSE 3  -- Antes de la fecha de inicio, considerar que todos tienen 3 juegos
            END as white_weekly_games,
            CASE 
                WHEN NOW() >= %s THEN COALESCE(w2.games_this_week, 0)
                ELSE 3  -- Antes de la fecha de inicio, considerar que todos tienen 3 juegos
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
            p.name,
            CASE 
                WHEN NOW() >= %s THEN COALESCE(w.games_this_week, 0)
                ELSE 3  -- Antes de la fecha de inicio, considerar que todos tienen 3 juegos
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
    
    cur.close()
    conn.close()
    
    return games, players

def get_weeks_stats():
    conn = get_db()
    cur = conn.cursor()
    
    # Obtener la fecha actual y el inicio de la semana
    now = datetime.now()
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # Contar juegos por jugador en la última semana
    cur.execute('''
        SELECT p.name, COUNT(g.id) as games_this_week
        FROM players p
        LEFT JOIN (
            SELECT white as player, id, date FROM games
            WHERE date >= %s
            UNION ALL
            SELECT black as player, id, date FROM games
            WHERE date >= %s
        ) g ON p.name = g.player
        GROUP BY p.name
    ''', (week_start, week_start))
    
    weekly_games = {row['name']: row['games_this_week'] for row in cur.fetchall()}
    
    cur.close()
    conn.close()
    return weekly_games

def calculate_ratings_with_changes():
    conn = get_db()
    cur = conn.cursor()
    
    # Obtener ratings iniciales desde start.json
    with open('start.json', 'r', encoding='utf-8') as f:
        start_data = json.load(f)
        initial_ratings = {p['name']: p['rating'] for p in start_data['players']}
    
    # Obtener todos los juegos ordenados por fecha
    cur.execute('SELECT white, black, result, date FROM games ORDER BY date')
    games = [dict(row) for row in cur.fetchall()]
    
    # Empezar desde los ratings iniciales
    current_ratings = initial_ratings.copy()
    elo_changes = []
    
    # Procesar juegos en orden cronológico y guardar ratings históricos
    historical_ratings = []
    for game in games:
        white_rating = current_ratings[game['white']]
        black_rating = current_ratings[game['black']]
        result = game['result']
        
        # Guardar ratings antes del juego
        historical_ratings.append({
            'white_rating': white_rating,
            'black_rating': black_rating
        })
        
        new_white, new_black = getElo(white_rating, black_rating, 50, result)
        
        white_change = new_white - white_rating
        black_change = new_black - black_rating
        
        current_ratings[game['white']] = new_white
        current_ratings[game['black']] = new_black
        
        elo_changes.append({
            'white_change': white_change,
            'black_change': black_change
        })
    
    # Aplicar penalizaciones semanales al final
    now = datetime.now()
    week_start = now - timedelta(days=now.weekday())
    week_start = week_start.replace(hour=0, minute=0, second=0, microsecond=0)
    
    weekly_games = get_weeks_stats()
    for player, games_count in weekly_games.items():
        if games_count < 3:
            # Penalización más suave: -10 puntos por juego faltante
            missing_games = 3 - games_count
            penalty = -10 * missing_games
            current_ratings[player] += penalty
    
    cur.close()
    conn.close()
    
    return current_ratings, elo_changes, historical_ratings

def GetProbability(rating1, rating2):
    return 1 / (1 + 10 ** ((rating2 - rating1) / 400))

def getElo(ratingOfPlayer1, ratingOfPlayer2, K, result):
    # Calcular probabilidad de victoria para el jugador 1
    expected = GetProbability(ratingOfPlayer1, ratingOfPlayer2)
    
    # El resultado actual (1 = victoria, 0.5 = empate, 0 = derrota)
    actual = result
    
    # Calcular el cambio de ELO
    change = K * (actual - expected)
    
    # Aplicar el cambio (redondeado a entero)
    newRatingOfPlayer1 = int(round(ratingOfPlayer1 + change))
    newRatingOfPlayer2 = int(round(ratingOfPlayer2 - change))
    
    return newRatingOfPlayer1, newRatingOfPlayer2

def format_name(full_name):
    parts = full_name.split()
    if len(parts) > 1:
        return f"{parts[0]} {parts[-1][0]}."
    return full_name

# Diccionario para almacenar los intentos de login por IP
login_attempts = {}
# Diccionario para almacenar las últimas acciones por usuario
user_actions = {}
# Rate limiting para sugerencias de partidas
suggestion_timestamps = {}

def rate_limit(max_requests=5, window=60):
    """
    Decorador para limitar peticiones por IP
    max_requests: número máximo de peticiones permitidas
    window: ventana de tiempo en segundos
    """
    def decorator(f):
        @wraps(f)
        def wrapped(*args, **kwargs):
            ip = request.remote_addr
            now = time.time()
            
            # Limpiar registros antiguos
            if ip in suggestion_timestamps:
                suggestion_timestamps[ip] = [t for t in suggestion_timestamps[ip] if now - t < window]
            else:
                suggestion_timestamps[ip] = []
            
            if len(suggestion_timestamps[ip]) >= max_requests:
                return jsonify({'error': 'Demasiadas peticiones. Por favor espera un momento.'}), 429
            
            suggestion_timestamps[ip].append(now)
            return f(*args, **kwargs)
        return wrapped
    return decorator

@app.route('/')
def index():
    games, players_data = load_league_data()
    
    # Calcular ratings (en memoria)
    with open('start.json', 'r', encoding='utf-8') as f:
        start_data = json.load(f)
        current_ratings = {p['name']: p['rating'] for p in start_data['players']}
    
    # Procesar juegos y calcular cambios
    processed_games = []
    for game in games:
        white_rating = current_ratings[game['white']]
        black_rating = current_ratings[game['black']]
        
        new_white, new_black = getElo(white_rating, black_rating, 50, game['result'])
        white_change = new_white - white_rating
        black_change = new_black - black_rating
        
        processed_games.append({
            **game,
            'white_display': format_name(game['white']),
            'black_display': format_name(game['black']),
            'white_rating': white_rating,
            'black_rating': black_rating,
            'white_change': white_change,
            'black_change': black_change
        })
        
        current_ratings[game['white']] = new_white
        current_ratings[game['black']] = new_black
    
    # Preparar datos de jugadores
    players = [{
        'name': p['name'],
        'display_name': format_name(p['name']),
        'rating': current_ratings[p['name']],
        'games_this_week': p['games_this_week'],
        'warning': p['games_this_week'] < 3
    } for p in players_data]
    
    players.sort(key=lambda x: x['rating'], reverse=True)
    
    return render_template('index.html',
                         players=players,
                         games=processed_games,
                         is_admin=current_user.is_admin if not current_user.is_anonymous else False)

@app.route('/add_game', methods=['POST'])
@login_required
def add_game():
    if not current_user.is_admin:
        flash('Solo los administradores pueden agregar partidas')
        return redirect(url_for('index'))
        
    # Anti-spam para agregar partidas
    user_id = current_user.id
    now = datetime.now()
    if user_id in user_actions:
        last_action = user_actions[user_id]
        if now - last_action < timedelta(seconds=2):
            flash('Por favor espera un momento antes de agregar otra partida')
            return redirect(url_for('index'))
    
    user_actions[user_id] = now
    
    # Validación de entrada
    white = request.form.get('white')
    black = request.form.get('black')
    result = request.form.get('result')
    
    if not all([white, black, result]) or white == black:
        flash('Datos inválidos')
        return redirect(url_for('index'))
        
    try:
        result = float(result)
        if result not in [0, 0.5, 1]:
            raise ValueError
    except ValueError:
        flash('Resultado inválido')
        return redirect(url_for('index'))
    
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute(
        'INSERT INTO games (white, black, result, date) VALUES (%s, %s, %s, %s)',
        (white, black, result, datetime.now())
    )
    
    conn.commit()
    cur.close()
    conn.close()
    
    return redirect(url_for('index'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.remote_addr
        now = datetime.now()
        conn = None
        cur = None
        
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            
            # Log de intento de login
            logger.info(f"Intento de login para usuario: {username}")
            
            # Validación básica de entrada
            if not username or not password or len(username) > 50 or len(password) > 100:
                flash('Datos de entrada inválidos')
                return render_template('login.html')
            
            # Verificar intentos de login fallidos
            if ip in login_attempts:
                attempts, last_attempt = login_attempts[ip]
                if attempts >= 5 and now - last_attempt < timedelta(minutes=15):
                    flash('Demasiados intentos fallidos. Por favor espera 15 minutos.')
                    return render_template('login.html')
                elif now - last_attempt > timedelta(minutes=15):
                    login_attempts[ip] = (0, now)
            
            # Intentar conexión a la base de datos
            conn = get_db()
            cur = conn.cursor()
            
            # Buscar usuario
            cur.execute('SELECT * FROM users WHERE username = %s', (username,))
            user = cur.fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                user_obj = User(user['id'], user['username'], user['is_admin'])
                login_user(user_obj)
                
                # Resetear intentos fallidos
                if ip in login_attempts:
                    del login_attempts[ip]
                
                logger.info(f"Login exitoso para usuario: {username}")
                return redirect(url_for('index'))
            
            # Incrementar contador de intentos fallidos
            attempts = login_attempts.get(ip, (0, now))[0] + 1
            login_attempts[ip] = (attempts, now)
            
            logger.warning(f"Login fallido para usuario: {username}")
            flash('Usuario o contraseña incorrectos')
            
        except Exception as e:
            logger.error(f"Error en login: {str(e)}", exc_info=True)
            flash('Error al intentar iniciar sesión. Por favor intenta más tarde.')
            return render_template('login.html')
            
        finally:
            if cur:
                cur.close()
            if conn:
                try:
                    conn.close()
                except Exception as e:
                    logger.error(f"Error al cerrar conexión: {str(e)}")
    
    return render_template('login.html')

@app.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('index'))

def get_player_game_counts():
    conn = get_db()
    cur = conn.cursor()
    
    # Contar juegos por jugador
    cur.execute('''
        SELECT p.name, COUNT(g.id) as games
        FROM players p
        LEFT JOIN (
            SELECT white as player, id FROM games
            UNION ALL
            SELECT black as player, id FROM games
        ) g ON p.name = g.player
        GROUP BY p.name
    ''')
    player_counts = {row['name']: row['games'] for row in cur.fetchall()}
    
    # Contar juegos entre pares de jugadores
    cur.execute('''
        SELECT 
            LEAST(white, black) as p1,
            GREATEST(white, black) as p2,
            COUNT(*) as games
        FROM games
        GROUP BY LEAST(white, black), GREATEST(white, black)
    ''')
    pair_counts = {(row['p1'], row['p2']): row['games'] for row in cur.fetchall()}
    
    cur.close()
    conn.close()
    return player_counts, pair_counts

@app.route('/suggest_match')
@rate_limit(max_requests=5, window=60)
@login_required
def suggest_match():
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Obtener todos los jugadores
        cur.execute('SELECT name FROM players')
        players = [row['name'] for row in cur.fetchall()]
        
        cur.close()
        conn.close()
        
        player_counts, pair_counts = get_player_game_counts()
        
        # Encontrar todas las posibles parejas y sus puntuaciones
        pairs = []
        for i, p1 in enumerate(players):
            for p2 in players[i+1:]:
                pair = tuple(sorted([p1, p2]))
                games_between = pair_counts.get(pair, 0)
                
                # Calcular puntuación (menor es mejor)
                score = games_between * 10  # Prioridad alta a parejas con pocos juegos
                
                # Penalizar si algún jugador tiene muchos más juegos que el promedio
                avg_games = sum(player_counts.values()) / len(player_counts)
                score += abs(player_counts[p1] - avg_games)
                score += abs(player_counts[p2] - avg_games)
                
                # Agregar algo de aleatoriedad
                from random import uniform
                score += uniform(0, 5)
                
                pairs.append((score, p1, p2))
        
        # Ordenar por puntuación y tomar uno de los mejores
        pairs.sort()
        from random import randint
        selected_index = randint(0, min(2, len(pairs)-1))
        
        if not pairs:
            return jsonify({'error': 'No hay suficientes jugadores'})
        
        _, p1, p2 = pairs[selected_index]
        
        # Nueva conexión para la segunda consulta
        conn = get_db()
        cur = conn.cursor()
        
        # Decidir colores basado en historial
        cur.execute('''
            SELECT white, black 
            FROM games 
            WHERE (white = %s OR black = %s OR white = %s OR black = %s)
            ORDER BY date DESC
            LIMIT 1
        ''', (p1, p1, p2, p2))
        last_game = cur.fetchone()
        
        cur.close()
        conn.close()
        
        if last_game:
            if last_game['white'] == p1 or last_game['black'] == p2:
                white, black = p2, p1
            else:
                white, black = p1, p2
        else:
            from random import choice
            if choice([True, False]):
                white, black = p1, p2
            else:
                white, black = p2, p1
        
        return jsonify({
            'white': white,
            'black': black,
            'white_display': format_name(white),
            'black_display': format_name(black)
        })
        
    except Exception as e:
        if cur:
            cur.close()
        if conn:
            conn.close()
        raise e

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')

if __name__ == '__main__':
    init_db()
    app.run() 