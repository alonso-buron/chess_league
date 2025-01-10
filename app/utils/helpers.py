def format_name(full_name):
    parts = full_name.split()
    if len(parts) > 1:
        return f"{parts[0]} {parts[-1][0]}."
    return full_name

def get_players():
    """Obtener lista de jugadores para el formulario de registro"""
    from app.database.connection import get_db
    
    conn = get_db()
    cur = conn.cursor()
    cur.execute('SELECT name FROM players ORDER BY name')
    players = [{'name': row['name'], 'display_name': format_name(row['name'])} for row in cur.fetchall()]
    cur.close()
    conn.close()
    return players 