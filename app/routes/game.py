from flask import Blueprint, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.database.connection import get_db
from datetime import datetime, timedelta
import logging

bp = Blueprint('game', __name__, url_prefix='/game')

# Diccionario para almacenar las últimas acciones por usuario
user_actions = {}

@bp.route('/add_game', methods=['POST'])
@login_required
def add_game():
    if not current_user.is_admin and not current_user.player_name:
        flash('No tienes permiso para agregar partidas')
        return redirect(url_for('main.index'))
        
    # Anti-spam para agregar partidas
    user_id = current_user.id
    now = datetime.now()
    if user_id in user_actions:
        last_action = user_actions[user_id]
        if now - last_action < timedelta(seconds=2):
            flash('Por favor espera un momento antes de agregar otra partida')
            return redirect(url_for('main.index'))
    
    user_actions[user_id] = now
    
    # Validación de entrada
    white_id = request.form.get('white')
    black_id = request.form.get('black')
    result = request.form.get('result')
    
    if not all([white_id, black_id, result]) or white_id == black_id:
        flash('Datos inválidos')
        return redirect(url_for('main.index'))
    
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Obtener nombres de jugadores por ID
        cur.execute('SELECT id, name FROM players WHERE id IN (%s, %s)', (white_id, black_id))
        players = {str(row['id']): row['name'] for row in cur.fetchall()}
        
        if len(players) != 2:
            flash('Jugadores no encontrados')
            return redirect(url_for('main.index'))
        
        white_name = players[white_id]
        black_name = players[black_id]
            
        # Verificar que el usuario sea parte del juego si no es admin
        if not current_user.is_admin:
            if current_user.player_name not in [white_name, black_name]:
                flash('Solo puedes agregar partidas en las que hayas participado')
                return redirect(url_for('main.index'))
            
        try:
            result = float(result)
            if result not in [0, 0.5, 1]:
                raise ValueError
        except ValueError:
            flash('Resultado inválido')
            return redirect(url_for('main.index'))
        
        has_lettuce_factor = bool(request.form.get('has_lettuce_factor'))
        
        cur.execute(
            'INSERT INTO games (white, black, result, date, added_by, has_lettuce_factor) VALUES (%s, %s, %s, %s, %s, %s)',
            (white_name, black_name, result, datetime.now(), current_user.id, has_lettuce_factor)
        )
        
        conn.commit()
        flash('Partida agregada exitosamente')
        
    except Exception as e:
        logging.error(f"Error al crear juego: {str(e)}")
        flash('Error al crear el juego')
        conn.rollback()
        
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('main.index')) 