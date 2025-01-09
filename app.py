from flask import Flask, render_template, request, redirect, url_for, flash, jsonify
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user, logout_user
from datetime import datetime
import os
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import DictCursor
from werkzeug.security import generate_password_hash, check_password_hash

# Cargar variables de entorno desde .env en desarrollo
load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database setup
def get_db():
    connection = psycopg2.connect(os.environ.get('POSTGRES_URL'))
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

def load_league():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT white, black, result, date FROM games ORDER BY date DESC')
    games = [dict(row) for row in cur.fetchall()]
    
    cur.execute('SELECT name, initial_rating FROM players')
    players = [dict(row) for row in cur.fetchall()]
    
    cur.close()
    conn.close()
    
    return {'games': games, 'players': players}

def calculate_ratings_with_changes():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT name, initial_rating FROM players')
    players = [dict(row) for row in cur.fetchall()]
    
    cur.execute('SELECT white, black, result FROM games ORDER BY date')
    games = [dict(row) for row in cur.fetchall()]
    
    current_ratings = {p['name']: p['initial_rating'] for p in players}
    elo_changes = []  # Lista para guardar los cambios de cada juego
    
    for game in games:
        white_rating = current_ratings[game['white']]
        black_rating = current_ratings[game['black']]
        result = game['result']
        
        new_white, new_black = getElo(white_rating, black_rating, 50, result)
        
        # Guardar cambios de ELO
        white_change = new_white - white_rating
        black_change = new_black - black_rating
        elo_changes.append({
            'white_change': white_change,
            'black_change': black_change
        })
        
        # Actualizar ratings
        current_ratings[game['white']] = new_white
        current_ratings[game['black']] = new_black
    
    cur.close()
    conn.close()
    
    return current_ratings, elo_changes

def GetProbability(rating1, rating2):
    return 1 / (1 + 10 ** ((rating1 - rating2) / 400))

def getElo(ratingOfPlayer1, ratingOfPlayer2, K, result):
    if ratingOfPlayer1 >= ratingOfPlayer2:
        higherRating = ratingOfPlayer1
        lowerRating = ratingOfPlayer2
    else:
        higherRating = ratingOfPlayer2
        lowerRating = ratingOfPlayer1
    expectedScore = GetProbability(higherRating, lowerRating)
    eloChange = K * (1 - expectedScore)
    if result == 1:
        newRatingOfPlayer1 = int(round(ratingOfPlayer1 + eloChange, 1))
        newRatingOfPlayer2 = int(round(ratingOfPlayer2 - eloChange, 1))
    else:
        newRatingOfPlayer1 = int(round(ratingOfPlayer1 - eloChange, 1))
        newRatingOfPlayer2 = int(round(ratingOfPlayer2 + eloChange, 1))
    return newRatingOfPlayer1, newRatingOfPlayer2

def format_name(full_name):
    parts = full_name.split()
    if len(parts) > 1:
        return f"{parts[0]} {parts[-1][0]}."
    return full_name

@app.route('/')
def index():
    league_data = load_league()
    ratings, elo_changes = calculate_ratings_with_changes()
    
    # Ordenar jugadores por rating
    players = [{'name': name, 'rating': rating, 'display_name': format_name(name)} 
              for name, rating in ratings.items()]
    players.sort(key=lambda x: x['rating'], reverse=True)
    
    # Agregar display_name a los juegos
    games_with_changes = []
    for game, changes in zip(league_data['games'], elo_changes):
        games_with_changes.append({
            **game,
            'white_display': format_name(game['white']),
            'black_display': format_name(game['black']),
            'white_change': changes['white_change'],
            'black_change': changes['black_change']
        })
    
    return render_template('index.html', 
                         players=players,
                         games=games_with_changes,
                         is_admin=current_user.is_admin if not current_user.is_anonymous else False)

@app.route('/add_game', methods=['POST'])
@login_required
def add_game():
    if not current_user.is_admin:
        flash('Solo administradores pueden agregar partidas')
        return redirect(url_for('index'))
    
    white = request.form['white']
    black = request.form['black']
    result = float(request.form['result'])
    
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
        username = request.form['username']
        password = request.form['password']
        
        conn = get_db()
        cur = conn.cursor()
        cur.execute('SELECT * FROM users WHERE username = %s', (username,))
        user = cur.fetchone()
        cur.close()
        conn.close()
        
        if user and check_password_hash(user['password_hash'], password):
            login_user(User(user['id'], user['username'], user['is_admin']))
            return redirect(url_for('index'))
            
        flash('Usuario o contraseña inválidos')
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
def suggest_match():
    conn = get_db()
    cur = conn.cursor()
    
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
    
    # Decidir colores basado en historial
    cur = conn.cursor()
    cur.execute('''
        SELECT white, black 
        FROM games 
        WHERE (white = %s OR black = %s OR white = %s OR black = %s)
        ORDER BY date DESC
        LIMIT 1
    ''', (p1, p1, p2, p2))
    last_game = cur.fetchone()
    
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

if __name__ == '__main__':
    init_db()  # Inicializar base de datos
    app.run(debug=True) 