# conectar_db.py
import os
import sys
from datetime import datetime
from pathlib import Path
import pymysql

# Buscar el .env en la misma carpeta
BASE_DIR = Path(__file__).resolve().parent
ENV_FILE = BASE_DIR / ".env"

# Leer el .env manualmente, ignorando la terminal
def leer_env():
    config = {}
    if ENV_FILE.exists():
        with ENV_FILE.open("r", encoding="utf-8-sig") as f:
            for linea in f:
                linea = linea.strip()
                if linea and not linea.startswith("#") and "=" in linea:
                    k, v = linea.split("=", 1)
                    config[k.strip()] = v.strip()
    return config

def main():
    print("=" * 60)
    print(f"Prueba de conexión (Python {sys.version_info[0]}.{sys.version_info[1]})")

    config = leer_env()
    
    host = config.get("DB_HOST")
    puerto = config.get("DB_PORT")
    usuario = config.get("DB_USER")
    password = config.get("DB_PASSWORD", "")
    base = config.get("DB_NAME")

    if not host:
        print(" ERROR DE CONFIGURACIÓN: Falta DB_HOST en el archivo .env")
        print(" Resultado: CONEXIÓN FALLIDA")
        print("=" * 60)
        return

    try:
        conexion = pymysql.connect(
            host=host,
            port=int(puerto),
            user=usuario,
            password=password,
            database=base,
            charset="utf8mb4"
        )
        
        with conexion.cursor() as cur:
            cur.execute("SELECT VERSION()")
            version = cur.fetchone()[0]
            cur.execute("SELECT DATABASE()")
            base_actual = cur.fetchone()[0]
            cur.execute("SHOW TABLES")
            tablas = len(cur.fetchall())

        print(f"  Host     : {host}:{puerto}")
        print(f"  Motor    : MariaDB/MySQL {version}")
        print(f"  Base     : {base_actual} ({tablas} tablas)")
        print("  Resultado: Conexión establecida")
        
    except Exception as e:
        print(f"  ERROR: {e}")
        print("  Resultado: CONEXIÓN FALLIDA")
        
    print("=" * 60)
    conexion.close()

if __name__ == "__main__":
    main()