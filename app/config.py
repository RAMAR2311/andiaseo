import os
from pathlib import Path
from dotenv import load_dotenv

# Cargar variables de entorno desde .env si existe
basedir = Path(__file__).resolve().parent.parent
load_dotenv(basedir / '.env')

class Config:
    """Configuración base de la aplicación Andiaseo."""
    SECRET_KEY = os.environ.get('SECRET_KEY') or 'andiaseo-super-secret-production-key-2026'
    
    # Manejo de DATABASE_URL para PostgreSQL o fallback a SQLite local
    database_url = os.environ.get('DATABASE_URL')
    if database_url:
        if database_url.startswith('postgres://'):
            database_url = database_url.replace('postgres://', 'postgresql://', 1)
        SQLALCHEMY_DATABASE_URI = database_url
    else:
        # Base de datos SQLite por defecto en el directorio raíz
        SQLALCHEMY_DATABASE_URI = f"sqlite:///{basedir / 'andiaseo_inventory.db'}"

    SQLALCHEMY_TRACK_MODIFICATIONS = False
    
    # Configuración de sesión y cookies
    SESSION_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_HTTPONLY = True
    REMEMBER_COOKIE_DURATION = 86400 * 7  # 7 días
