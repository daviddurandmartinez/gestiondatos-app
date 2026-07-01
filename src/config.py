import streamlit as st
import sys
from decouple import config

def get_sql_server_configs():
    try:
        # Credenciales base del servidor
        base_config = {
            "DRIVER": config("DRIVER"),
            "SERVER": config("SERVER"),
            "USER": config("USER"),    
            "PASSWORD": config("PASSWORD"),
        }
        
        # Diccionario con ambas configuraciones de BD
        return {
            "RRHH": {**base_config, "DATABASE": config("DATABASE_RRHH")},
            "GESTION": {**base_config, "DATABASE": config("DATABASE_GESTION")}
        }
    except Exception as e:
        if 'streamlit' in sys.modules and st.runtime.exists():
            st.error(f"Error al cargar las configuraciones de base de datos: {e}")
        return None

# Cargar el diccionario con ambas configuraciones
SQL_CONFIGS = get_sql_server_configs()

# Validar y extraer configuraciones individuales de forma segura
if SQL_CONFIGS and all(all(db.values()) for db in SQL_CONFIGS.values()):
    SQL_SERVER_CONFIG_RRHH = SQL_CONFIGS["RRHH"]
    SQL_SERVER_CONFIG_GESTION = SQL_CONFIGS["GESTION"]
    
    # Constantes de la aplicación vinculadas a db_gestion_datos
    TARGET_TABLE = "dbo.retiro_temporal" 
    KEY_COLUMN = "id" 
else:
    SQL_SERVER_CONFIG_RRHH = None
    SQL_SERVER_CONFIG_GESTION = None
    TARGET_TABLE = "ERROR_TABLE_CHECK_CONFIG"
    KEY_COLUMN = "ERROR_ID_CHECK_CONFIG"

FILE_ENCODING = 'utf-8'

