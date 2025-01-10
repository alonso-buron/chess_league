from flask import Flask
from flask_login import LoginManager
from werkzeug.middleware.proxy_fix import ProxyFix
import logging
import sys
from dotenv import load_dotenv
import os

# Configurar logging
logging.basicConfig(stream=sys.stdout, level=logging.INFO)
logger = logging.getLogger(__name__)

# Cargar variables de entorno
load_dotenv()

def create_app():
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)
    app.secret_key = os.environ.get('SECRET_KEY', 'dev_key')

    # Inicializar Login Manager
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'login'

    # Registrar blueprints
    from app.routes import blueprints
    for blueprint in blueprints:
        app.register_blueprint(blueprint, url_prefix=None)

    # Configurar el user loader
    from app.models import User
    @login_manager.user_loader
    def load_user(user_id):
        from app.database import get_db
        conn = get_db()
        cur = conn.cursor()
        cur.execute(
            'SELECT id, username, is_admin, COALESCE(player_name, NULL) as player_name FROM users WHERE id = %s', 
            (user_id,)
        )
        user = cur.fetchone()
        cur.close()
        conn.close()
        if user:
            return User(user['id'], user['username'], user['is_admin'], user['player_name'])
        return None

    return app 