import os
from flask import Flask, redirect, url_for, render_template
from flask_login import LoginManager, current_user
from config import Config
from database import get_db, init_db
from utils.helpers import format_date, format_datetime, format_currency, time_ago


# ── User class for Flask-Login ─────────────────────────────
class User:
    def __init__(self, row):
        self.id = row['id']
        self.email = row['email']
        self.role = row['role']
        self.full_name = row['full_name']
        self.phone = row['phone']
        self.avatar = row['avatar']
        self.is_active_flag = row['is_active']

    @property
    def is_authenticated(self):
        return True

    @property
    def is_active(self):
        return bool(self.is_active_flag)

    @property
    def is_anonymous(self):
        return False

    def get_id(self):
        return str(self.id)


# ── App Factory ────────────────────────────────────────────
def create_app():
    app = Flask(__name__, template_folder='../frontend/templates', static_folder='../frontend/static')
    app.config.from_object(Config)

    # Ensure upload folder exists
    os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'logos'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'avatars'), exist_ok=True)
    os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'payments'), exist_ok=True)

    # ── Flask-Login Setup ──────────────────────────────────
    login_manager = LoginManager()
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    login_manager.login_message_category = 'warning'

    @login_manager.user_loader
    def load_user(user_id):
        db = get_db()
        row = db.execute('SELECT * FROM users WHERE id = ?', (user_id,)).fetchone()
        db.close()
        if row:
            return User(row)
        return None

    # ── Template context processors ────────────────────────
    @app.context_processor
    def inject_helpers():
        return {
            'format_date': format_date,
            'format_datetime': format_datetime,
            'format_currency': format_currency,
            'time_ago': time_ago,
        }

    # ── Register Blueprints ────────────────────────────────
    from routes.auth import auth_bp
    from routes.public import public_bp
    from routes.admin import admin_bp
    from routes.member import member_bp
    from routes.trainer import trainer_bp
    from routes.api import api_bp
    from routes.sysadmin import sysadmin_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(public_bp)
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(member_bp, url_prefix='/member')
    app.register_blueprint(trainer_bp, url_prefix='/trainer')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(sysadmin_bp, url_prefix='/sysadmin')

    # ── Error Handlers ─────────────────────────────────────
    @app.errorhandler(403)
    def forbidden(e):
        return render_template('errors/403.html'), 403

    @app.errorhandler(404)
    def not_found(e):
        return render_template('errors/404.html'), 404

    @app.errorhandler(500)
    def server_error(e):
        return render_template('errors/500.html'), 500

    return app


# ── Entry Point ────────────────────────────────────────────
if __name__ == '__main__':
    init_db()
    app = create_app()
    app.run(debug=True, host='0.0.0.0', port=5000)
