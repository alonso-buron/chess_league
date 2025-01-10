from app import create_app
from app.database.connection import init_db
from app.database.migrations import run_migrations

app = create_app()

if __name__ == '__main__':
    run_migrations()
    init_db()
    app.run(debug=True, host='0.0.0.0', port=5000) 