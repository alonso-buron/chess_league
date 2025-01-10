from flask import Blueprint, request, redirect, url_for, flash
from flask_login import login_required, current_user
from app.database.connection import get_db
import json
import logging

bp = Blueprint('player', __name__, url_prefix='/player')

@bp.route('/add_player', methods=['POST'])
@login_required
def add_player():
    if not current_user.is_admin:
        flash('Solo administradores pueden agregar jugadores')
        return redirect(url_for('main.index'))
        
    player_name = request.form.get('player_name')
    initial_rating = request.form.get('initial_rating')
    
    if not player_name or not initial_rating:
        flash('Nombre y rating inicial son requeridos')
        return redirect(url_for('main.index'))
        
    try:
        initial_rating = int(initial_rating)
    except ValueError:
        flash('El rating inicial debe ser un número')
        return redirect(url_for('main.index'))
        
    conn = get_db()
    cur = conn.cursor()
    
    try:
        # Verificar si el jugador ya existe en la base de datos
        cur.execute('SELECT name FROM players WHERE name = %s', (player_name,))
        if cur.fetchone():
            flash('Este jugador ya existe')
            return redirect(url_for('main.index'))
        
        # Verificar y actualizar start.json primero
        try:
            with open('start.json', 'r', encoding='utf-8') as f:
                start_data = json.load(f)
            
            # Verificar si el jugador ya existe en start.json
            if any(p['name'] == player_name for p in start_data['players']):
                flash('Este jugador ya existe en start.json')
                return redirect(url_for('main.index'))
            
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
            
            conn.commit()
            flash('Jugador creado exitosamente')
                
        except Exception as e:
            logging.error(f"Error actualizando start.json: {str(e)}")
            conn.rollback()
            flash('Error al actualizar el archivo de ratings iniciales')
            return redirect(url_for('main.index'))
        
    except Exception as e:
        logging.error(f"Error al crear jugador: {str(e)}")
        flash('Error al crear el jugador')
        try:
            with open('start.json', 'r', encoding='utf-8') as f:
                start_data = json.load(f)
            start_data['players'] = [p for p in start_data['players'] if p['name'] != player_name]
            with open('start.json', 'w', encoding='utf-8') as f:
                json.dump(start_data, f, indent=4, ensure_ascii=False)
        except Exception as rollback_error:
            logging.error(f"Error al revertir cambios en start.json: {str(rollback_error)}")
        conn.rollback()
        
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('main.index')) 