# config.py
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

def cargar_env():
    """Lee el archivo .env manualmente sin dependencias externas."""
    config = {}
    if ENV_FILE.exists():
        with ENV_FILE.open("r", encoding="utf-8-sig") as f:
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k, v = linea.split("=", 1)
                    config[k.strip()] = v.strip()
    return config

env = cargar_env()

class Config:
    SECRET_KEY = env.get("SECRET_KEY", "default-inseguro")
    
    # La URI se construye AQUÍ, no en app.py
    _user = env.get("DB_USER", "root")
    _pass = env.get("DB_PASSWORD", "")
    _host = env.get("DB_HOST", "127.0.0.1")
    _port = env.get("DB_PORT", "3306")
    _name = env.get("DB_NAME", "desercion_escolar")
    
    SQLALCHEMY_DATABASE_URI = f"mysql+pymysql://{_user}:{_pass}@{_host}:{_port}/{_name}?charset=utf8mb4"
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 280,
        "pool_size": 5,
        "max_overflow": 10,
    }