from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_user, logout_user, login_required
from app.models.user import User
from app.database.connection import get_db
from werkzeug.security import check_password_hash, generate_password_hash
from datetime import datetime, timedelta
import logging

bp = Blueprint('auth', __name__, url_prefix='/auth')

# Diccionario para almacenar los intentos de login por IP
login_attempts = {}

@bp.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        ip = request.remote_addr
        now = datetime.now()
        conn = None
        cur = None
        
        try:
            username = request.form.get('username')
            password = request.form.get('password')
            
            logging.info(f"Intento de login para usuario: {username}")
            
            if not username or not password or len(username) > 50 or len(password) > 100:
                flash('Datos de entrada inválidos')
                return render_template('login.html')
            
            if ip in login_attempts:
                attempts, last_attempt = login_attempts[ip]
                if attempts >= 5 and now - last_attempt < timedelta(minutes=15):
                    flash('Demasiados intentos fallidos. Por favor espera 15 minutos.')
                    return render_template('login.html')
                elif now - last_attempt > timedelta(minutes=15):
                    login_attempts[ip] = (0, now)
            
            conn = get_db()
            cur = conn.cursor()
            
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
                
                if ip in login_attempts:
                    del login_attempts[ip]
                
                logging.info(f"Login exitoso para usuario: {username}")
                return redirect(url_for('main.index'))
            
            attempts = login_attempts.get(ip, (0, now))[0] + 1
            login_attempts[ip] = (attempts, now)
            
            logging.warning(f"Login fallido para usuario: {username}")
            flash('Usuario o contraseña incorrectos')
            
        except Exception as e:
            logging.error(f"Error en login: {str(e)}", exc_info=True)
            flash('Error al intentar iniciar sesión. Por favor intenta más tarde.')
            return render_template('login.html')
            
        finally:
            if cur:
                cur.close()
            if conn:
                conn.close()
    
    return render_template('login.html')

@bp.route('/logout')
@login_required
def logout():
    logout_user()
    return redirect(url_for('main.index'))

@bp.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if not username or not password:
            flash('Usuario y contraseña son requeridos')
            return render_template('register.html')
            
        conn = get_db()
        cur = conn.cursor()
        
        try:
            # Verificar si el usuario ya existe
            cur.execute('SELECT id FROM users WHERE username = %s', (username,))
            if cur.fetchone():
                flash('El usuario ya existe')
                return render_template('register.html')
            
            # Crear nuevo usuario
            cur.execute(
                'INSERT INTO users (username, password) VALUES (%s, %s)',
                (username, generate_password_hash(password))
            )
            conn.commit()
            flash('Usuario registrado exitosamente')
            return redirect(url_for('login'))
            
        except Exception as e:
            logging.error(f"Error en registro: {str(e)}")
            flash('Error al registrar usuario')
            return render_template('register.html')
            
        finally:
            cur.close()
            conn.close()
    
    return render_template('register.html') 