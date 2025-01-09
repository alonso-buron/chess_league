from flask import Flask, render_template, request, redirect, url_for, flash
from flask_login import LoginManager, UserMixin, login_user, login_required, current_user
from datetime import datetime
import os
import psycopg2
from psycopg2.extras import DictCursor
from werkzeug.security import generate_password_hash, check_password_hash
from urllib.parse import urlparse

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev_key')

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = 'login'

# Database setup
def get_db():
    url = urlparse(os.environ.get('POSTGRES_URL'))
    connection = psycopg2.connect(
        dbname=url.path[1:],
        user=url.username,
        password=url.password,
        host=url.hostname,
        port=url.port
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

def calculate_ratings():
    conn = get_db()
    cur = conn.cursor()
    
    cur.execute('SELECT name, initial_rating FROM players')
    players = [dict(row) for row in cur.fetchall()]
    
    cur.execute('SELECT white, black, result FROM games ORDER BY date')
    games = [dict(row) for row in cur.fetchall()]
    
    current_ratings = {p['name']: p['initial_rating'] for p in players}
    
    for game in games:
        white_rating = current_ratings[game['white']]
        black_rating = current_ratings[game['black']]
        result = game['result']
        
        new_white, new_black = getElo(white_rating, black_rating, 50, result)
        current_ratings[game['white']] = new_white
        current_ratings[game['black']] = new_black
    
    cur.close()
    conn.close()
    
    return current_ratings

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

@app.route('/')
def index():
    league_data = load_league()
    ratings = calculate_ratings()
    
    # Ordenar jugadores por rating
    players = [{'name': name, 'rating': rating} 
              for name, rating in ratings.items()]
    players.sort(key=lambda x: x['rating'], reverse=True)
    
    return render_template('index.html', 
                         players=players,
                         games=league_data['games'],
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

if __name__ == '__main__':
    init_db()  # Inicializar base de datos
    app.run(debug=True) 