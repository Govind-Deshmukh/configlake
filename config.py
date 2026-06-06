import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('SECRET_KEY') or os.urandom(32).hex()
    
    # Database configuration
    DATABASE_TYPE = os.environ.get('DATABASE_TYPE', 'sqlite')
    
    if DATABASE_TYPE.lower() == 'sqlite':
        SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL') or 'sqlite:///config_manager.db'
    elif DATABASE_TYPE.lower() == 'mysql':
        MYSQL_USER = os.environ.get('MYSQL_USER', 'root')
        MYSQL_PASSWORD = os.environ.get('MYSQL_PASSWORD', '')
        MYSQL_HOST = os.environ.get('MYSQL_HOST', 'localhost')
        MYSQL_PORT = os.environ.get('MYSQL_PORT', '3306')
        MYSQL_DB = os.environ.get('MYSQL_DB', 'config_manager')
        SQLALCHEMY_DATABASE_URI = f'mysql+pymysql://{MYSQL_USER}:{MYSQL_PASSWORD}@{MYSQL_HOST}:{MYSQL_PORT}/{MYSQL_DB}'
    elif DATABASE_TYPE.lower() == 'postgresql':
        PG_USER = os.environ.get('PG_USER', 'postgres')
        PG_PASSWORD = os.environ.get('PG_PASSWORD', '')
        PG_HOST = os.environ.get('PG_HOST', 'localhost')
        PG_PORT = os.environ.get('PG_PORT', '5432')
        PG_DB = os.environ.get('PG_DB', 'config_manager')
        SQLALCHEMY_DATABASE_URI = f'postgresql://{PG_USER}:{PG_PASSWORD}@{PG_HOST}:{PG_PORT}/{PG_DB}'
    
    SQLALCHEMY_TRACK_MODIFICATIONS = False

    WTF_CSRF_TIME_LIMIT = 3600  # 1 hour

    # Master key for envelope encryption of per-environment keys.
    # Must be a valid Fernet key. Generate with: python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    # Store as an environment variable — never commit this value.
    CONFIGLAKE_MASTER_KEY = os.environ.get('CONFIGLAKE_MASTER_KEY')
    
