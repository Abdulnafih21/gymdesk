import os

BASE_DIR = os.path.abspath(os.path.dirname(__file__))


class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY', 'gymdesk-secret-key-change-in-production')
    DATABASE = os.path.join(BASE_DIR, 'gymdesk.db')
    UPLOAD_FOLDER = os.path.join(os.path.dirname(BASE_DIR), 'frontend', 'static', 'uploads')
    MAX_CONTENT_LENGTH = 16 * 1024 * 1024  # 16MB max upload
    DEBUG = True
