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
    
    try:
        # Crear tablas si no existen
        cur.execute('''
            CREATE TABLE IF NOT EXISTS players (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                initial_rating INTEGER NOT NULL
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                player_name TEXT REFERENCES players(name)
            )
        ''')
        
        cur.execute('''
            CREATE TABLE IF NOT EXISTS games (
                id SERIAL PRIMARY KEY,
                white TEXT NOT NULL REFERENCES players(name),
                black TEXT NOT NULL REFERENCES players(name),
                result REAL NOT NULL,
                date TIMESTAMP NOT NULL,
                added_by INTEGER REFERENCES users(id),
                has_lettuce_factor BOOLEAN NOT NULL DEFAULT FALSE
            )
        ''')
        
        # Sincronizar jugadores entre start.json y la base de datos
        with open('start.json', 'r', encoding='utf-8') as f:
            start_data = json.load(f)
            
        # Obtener jugadores actuales en la base de datos
        cur.execute('SELECT name, initial_rating FROM players')
        db_players = {row['name']: row['initial_rating'] for row in cur.fetchall()}
        
        # Insertar o actualizar jugadores desde start.json
        for player in start_data['players']:
            if player['name'] not in db_players:
                # Insertar nuevo jugador
                cur.execute(
                    'INSERT INTO players (name, initial_rating) VALUES (%s, %s)',
                    (player['name'], player['rating'])
                )
            elif db_players[player['name']] != player['rating']:
                # Actualizar rating si es diferente
                cur.execute(
                    'UPDATE players SET initial_rating = %s WHERE name = %s',
                    (player['rating'], player['name'])
                )
        
        # Crear admin si no existe
        cur.execute(
            '''
            INSERT INTO users (username, password_hash, is_admin) 
            VALUES (%s, %s, %s)
            ON CONFLICT (username) DO UPDATE 
            SET is_admin = EXCLUDED.is_admin
            ''',
            ('admin', generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin')), True)
        )
        
        # Confirmar transacción
        conn.commit()
        
    except Exception as e:
        logger.error(f"Error en init_db: {str(e)}")
        conn.rollback()
        raise e
        
    finally:
        cur.close()
        conn.close()

class User(UserMixin):
    def __init__(self, id, username, is_admin, player_name=None):
        self.id = id
        self.username = username
        self.is_admin = is_admin
        self.player_name = player_name

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT id, username, is_admin, COALESCE(player_name, NULL) as player_name FROM users WHERE id = %s', (user_id,))
    user = cur.fetchone()
    cur.close()
    conn.close()
    if user:
        return User(user['id'], user['username'], user['is_admin'], user['player_name'])
    return None

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
        logger.error(f"Error cargando datos de la liga: {str(e)}")
        games = []
        players = []
        
    finally:
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
    
    # Ordenar juegos por fecha (más antiguo primero)
    games.sort(key=lambda x: x['date'])
    
    # Procesar juegos y calcular cambios
    processed_games = []
    historical_ratings = current_ratings.copy()  # Mantener una copia de los ratings históricos
    
    for game in games:
        # Verificar que ambos jugadores existan en current_ratings
        if game['white'] not in historical_ratings or game['black'] not in historical_ratings:
            logger.error(f"Jugador no encontrado en ratings: {game['white']} o {game['black']}")
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
            logger.error(f"Jugador no encontrado en ratings: {p['name']}")
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

@app.route('/add_game', methods=['POST'])
@login_required
def add_game():
    if not current_user.is_admin and not current_user.player_name:
        flash('No tienes permiso para agregar partidas')
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
    white_id = request.form.get('white')
    black_id = request.form.get('black')
    result = request.form.get('result')
    
    if not all([white_id, black_id, result]) or white_id == black_id:
        flash('Datos inválidos')
        return redirect(url_for('index'))
    
    conn = get_db()
    cur = conn.cursor()
    
    # Obtener nombres de jugadores por ID
    cur.execute('SELECT id, name FROM players WHERE id IN (%s, %s)', (white_id, black_id))
    players = {str(row['id']): row['name'] for row in cur.fetchall()}
    
    if len(players) != 2:
        flash('Jugadores no encontrados')
        return redirect(url_for('index'))
    
    white_name = players[white_id]
    black_name = players[black_id]
        
    # Verificar que el usuario sea parte del juego si no es admin
    if not current_user.is_admin:
        if current_user.player_name not in [white_name, black_name]:
            flash('Solo puedes agregar partidas en las que hayas participado')
            return redirect(url_for('index'))
        
    try:
        result = float(result)
        if result not in [0, 0.5, 1]:
            raise ValueError
    except ValueError:
        flash('Resultado inválido')
        return redirect(url_for('index'))
    
    try:
        has_lettuce_factor = bool(request.form.get('has_lettuce_factor'))
        
        cur.execute(
            'INSERT INTO games (white, black, result, date, added_by, has_lettuce_factor) VALUES (%s, %s, %s, %s, %s, %s)',
            (white_name, black_name, result, datetime.now(), current_user.id, has_lettuce_factor)
        )
        
        conn.commit()
        cur.close()
        conn.close()
        
        return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Error al crear juego: {str(e)}")
        flash('Error al crear el juego')
        # Intentar revertir los cambios en start.json
        try:
            with open('start.json', 'r', encoding='utf-8') as f:
                start_data = json.load(f)
            # Eliminar el juego si fue agregado
            start_data['players'] = [p for p in start_data['players'] if p['name'] != white_name]
            with open('start.json', 'w', encoding='utf-8') as f:
                json.dump(start_data, f, indent=4, ensure_ascii=False)
        except Exception as rollback_error:
            logger.error(f"Error al revertir cambios en start.json: {str(rollback_error)}")
        conn.rollback()
        
    finally:
        cur.close()
        conn.close()
    
    # Recargar la página después de agregar el juego
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
            cur.execute('''
                SELECT id, username, password_hash, is_admin, 
                       COALESCE(player_name, NULL) as player_name 
                FROM users 
                WHERE username = %s
            ''', (username,))
            user = cur.fetchone()
            
            if user and check_password_hash(user['password_hash'], password):
                user_obj = User(user['id'], user['username'], user['is_admin'], user['player_name'])
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

@app.route('/favicon.ico')
def favicon():
    return send_from_directory('static', 'favicon.ico')

def get_players():
    """Obtener lista de jugadores para el formulario de registro"""
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT name FROM players ORDER BY name')
    players = [{'name': row['name'], 'display_name': format_name(row['name'])} for row in cur.fetchall()]
    cur.close()
    conn.close()
    return players

@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        player_name = request.form.get('player_name')
        
        if not all([username, password]):  # player_name es opcional ahora
            flash('Usuario y contraseña son requeridos')
            return render_template('register.html', players=get_players())
            
        conn = get_db()
        cur = conn.cursor()
        
        try:
            # Verificar si el usuario ya existe
            cur.execute('SELECT id FROM users WHERE username = %s', (username,))
            if cur.fetchone():
                flash('El nombre de usuario ya está en uso')
                return render_template('register.html', players=get_players())
            
            if player_name:    
                # Verificar si el jugador existe y no está asociado a otro usuario
                cur.execute('SELECT name FROM players WHERE name = %s', (player_name,))
                if not cur.fetchone():
                    flash('El jugador no existe en la liga')
                    return render_template('register.html', players=get_players())
                    
                cur.execute('SELECT id FROM users WHERE player_name = %s', (player_name,))
                if cur.fetchone():
                    flash('Este jugador ya está asociado a otro usuario')
                    return render_template('register.html', players=get_players())
            
            # Crear el usuario
            cur.execute(
                'INSERT INTO users (username, password_hash, player_name) VALUES (%s, %s, %s)',
                (username, generate_password_hash(password), player_name)
            )
            
            conn.commit()
            flash('Usuario creado exitosamente')
            return redirect(url_for('login'))
            
        except Exception as e:
            logger.error(f"Error en registro: {str(e)}", exc_info=True)
            flash('Error al crear el usuario. Por favor intenta más tarde.')
            return render_template('register.html', players=get_players())
            
        finally:
            cur.close()
            conn.close()
    
    return render_template('register.html', players=get_players())

def reset_db():
    """Reiniciar la base de datos completamente"""
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Deshabilitar temporalmente las restricciones de foreign key
        cur.execute('SET CONSTRAINTS ALL DEFERRED')
        
        # Eliminar tablas en orden correcto
        cur.execute('DROP TABLE IF EXISTS games CASCADE')
        cur.execute('DROP TABLE IF EXISTS users CASCADE')
        cur.execute('DROP TABLE IF EXISTS players CASCADE')
        
        conn.commit()
        
        # Crear tablas en orden correcto
        cur.execute('''
            CREATE TABLE players (
                id SERIAL PRIMARY KEY,
                name TEXT UNIQUE NOT NULL,
                initial_rating INTEGER NOT NULL
            )
        ''')
        
        cur.execute('''
            CREATE TABLE users (
                id SERIAL PRIMARY KEY,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                is_admin BOOLEAN NOT NULL DEFAULT FALSE,
                player_name TEXT REFERENCES players(name)
            )
        ''')
        
        cur.execute('''
            CREATE TABLE games (
                id SERIAL PRIMARY KEY,
                white TEXT NOT NULL REFERENCES players(name),
                black TEXT NOT NULL REFERENCES players(name),
                result REAL NOT NULL,
                date TIMESTAMP NOT NULL,
                added_by INTEGER REFERENCES users(id)
            )
        ''')
        
        # Cargar jugadores iniciales desde start.json
        with open('start.json', 'r', encoding='utf-8') as f:
            start_data = json.load(f)
            for player in start_data['players']:
                cur.execute(
                    'INSERT INTO players (name, initial_rating) VALUES (%s, %s)',
                    (player['name'], player['rating'])
                )
        
        # Crear usuario admin
        cur.execute(
            'INSERT INTO users (username, password_hash, is_admin) VALUES (%s, %s, %s)',
            ('admin', generate_password_hash(os.environ.get('ADMIN_PASSWORD', 'admin')), True)
        )
        
        conn.commit()
        
    except Exception as e:
        conn.rollback()
        raise e
    finally:
        cur.close()
        conn.close()

@app.route('/reset_database', methods=['POST'])
@login_required
def reset_database():
    if not current_user.is_admin:
        flash('Solo el administrador puede reiniciar la base de datos')
        return redirect(url_for('index'))
    
    try:
        reset_db()
        flash('Base de datos reiniciada exitosamente')
    except Exception as e:
        logger.error(f"Error al reiniciar la base de datos: {str(e)}")
        flash('Error al reiniciar la base de datos')
    
    return redirect(url_for('index'))

@app.route('/add_player', methods=['POST'])
@login_required
def add_player():
    if not current_user.is_admin:
        flash('Solo administradores pueden agregar jugadores')
        return redirect(url_for('index'))
        
    player_name = request.form.get('player_name')
    initial_rating = request.form.get('initial_rating')
    
    if not player_name or not initial_rating:
        flash('Nombre y rating inicial son requeridos')
        return redirect(url_for('index'))
        
    try:
        initial_rating = int(initial_rating)
    except ValueError:
        flash('El rating inicial debe ser un número')
        return redirect(url_for('index'))
        
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Verificar si el jugador ya existe en la base de datos
        cur.execute('SELECT name FROM players WHERE name = %s', (player_name,))
        if cur.fetchone():
            flash('Este jugador ya existe')
            return redirect(url_for('index'))
        
        # Verificar y actualizar start.json primero
        try:
            with open('start.json', 'r', encoding='utf-8') as f:
                start_data = json.load(f)
            
            # Verificar si el jugador ya existe en start.json
            if any(p['name'] == player_name for p in start_data['players']):
                flash('Este jugador ya existe en start.json')
                return redirect(url_for('index'))
            
            # Agregar nuevo jugador a start.json
            start_data['players'].append({
                'name': player_name,
                'rating': initial_rating
            })
            
            # Guardar archivo actualizado
            with open('start.json', 'w', encoding='utf-8') as f:
                json.dump(start_data, f, indent=4, ensure_ascii=False)
                
            # Si start.json se actualizó correctamente, crear jugador en la base de datos
            cur.execute(
                'INSERT INTO players (name, initial_rating) VALUES (%s, %s)',
                (player_name, initial_rating)
            )
            
            # Confirmar transacción
            conn.commit()
            flash('Jugador creado exitosamente')
                
        except Exception as e:
            logger.error(f"Error actualizando start.json: {str(e)}")
            conn.rollback()
            flash('Error al actualizar el archivo de ratings iniciales')
            return redirect(url_for('index'))
        
    except Exception as e:
        logger.error(f"Error al crear jugador: {str(e)}")
        flash('Error al crear el jugador')
        # Intentar revertir los cambios en start.json
        try:
            with open('start.json', 'r', encoding='utf-8') as f:
                start_data = json.load(f)
            # Eliminar el jugador si fue agregado
            start_data['players'] = [p for p in start_data['players'] if p['name'] != player_name]
            with open('start.json', 'w', encoding='utf-8') as f:
                json.dump(start_data, f, indent=4, ensure_ascii=False)
        except Exception as rollback_error:
            logger.error(f"Error al revertir cambios en start.json: {str(rollback_error)}")
        conn.rollback()
        
    finally:
        cur.close()
        conn.close()
    
    # Recargar la página después de agregar el jugador
    return redirect(url_for('index'))

def add_lettuce_column():
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('''
            ALTER TABLE games 
            ADD COLUMN IF NOT EXISTS has_lettuce_factor BOOLEAN NOT NULL DEFAULT FALSE;
        ''')
        conn.commit()
        print("Columna has_lettuce_factor agregada exitosamente")
    except Exception as e:
        print(f"Error agregando columna: {str(e)}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

# Ejecutar una vez al inicio
if __name__ == '__main__':
    add_lettuce_column()
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000) 