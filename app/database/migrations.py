from .connection import get_db
import logging

logger = logging.getLogger(__name__)

def add_lettuce_column():
    """Agrega la columna has_lettuce_factor a la tabla games"""
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute('''
            ALTER TABLE games 
            ADD COLUMN IF NOT EXISTS has_lettuce_factor BOOLEAN NOT NULL DEFAULT FALSE;
        ''')
        conn.commit()
        logger.info("Columna has_lettuce_factor agregada exitosamente")
    except Exception as e:
        logger.error(f"Error agregando columna has_lettuce_factor: {str(e)}")
        conn.rollback()
    finally:
        cur.close()
        conn.close()

def run_migrations():
    """Ejecuta todas las migraciones en orden"""
    migrations = [
        add_lettuce_column,
        # Agregar aquí futuras migraciones en orden
    ]
    
    for migration in migrations:
        try:
            logger.info(f"Ejecutando migración: {migration.__name__}")
            migration()
        except Exception as e:
            logger.error(f"Error en migración {migration.__name__}: {str(e)}")
            raise

def reset_db():
    """Reinicia la base de datos eliminando todas las tablas"""
    conn = get_db()
    cur = conn.cursor()
    try:
        # Desactivar temporalmente las restricciones de clave foránea
        cur.execute('SET CONSTRAINTS ALL DEFERRED;')
        
        # Eliminar todas las tablas en orden correcto
        cur.execute('''
            DROP TABLE IF EXISTS games CASCADE;
            DROP TABLE IF EXISTS users CASCADE;
            DROP TABLE IF EXISTS players CASCADE;
        ''')
        
        conn.commit()
        logger.info("Base de datos reiniciada exitosamente")
    except Exception as e:
        logger.error(f"Error reiniciando la base de datos: {str(e)}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close()

# Función para crear una nueva migración
def create_migration(name, sql):
    """
    Helper para crear nuevas migraciones
    
    Ejemplo de uso:
    create_migration('add_timestamp_column', '''
        ALTER TABLE games
        ADD COLUMN created_at TIMESTAMP NOT NULL DEFAULT NOW();
    ''')
    """
    conn = get_db()
    cur = conn.cursor()
    try:
        cur.execute(sql)
        conn.commit()
        logger.info(f"Migración {name} ejecutada exitosamente")
    except Exception as e:
        logger.error(f"Error en migración {name}: {str(e)}")
        conn.rollback()
        raise
    finally:
        cur.close()
        conn.close() 