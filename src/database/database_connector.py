import pandas as pd
from sqlalchemy import create_engine, text
import urllib # Necesario para codificar la contraseña en la URI de SQLAlchemy
#from config import SQL_SERVER_CONFIG, TARGET_TABLE, KEY_COLUMN
from config import SQL_SERVER_CONFIG_RRHH, SQL_SERVER_CONFIG_GESTION, TARGET_TABLE, KEY_COLUMN
import warnings
import streamlit as st

#############################################
## CONEXION A SQL SERVER USANDO SQLALCHEMY ##
#############################################

def create_sqlalchemy_engine(db_type="GESTION"):
    """
    Crea un motor de SQLAlchemy. 
    db_type puede ser 'RRHH' o 'GESTION'. Por defecto es 'GESTION'.
    """
    # Elegir la configuración adecuada
    config_db = SQL_SERVER_CONFIG_RRHH if db_type == "RRHH" else SQL_SERVER_CONFIG_GESTION
    
    if not config_db:
        return None
    
    driver_name = config_db["DRIVER"].strip('{}')
    username = config_db["USER"]
    server = config_db["SERVER"]
    database = config_db["DATABASE"]
    password = urllib.parse.quote_plus(config_db["PASSWORD"])
    
    conn_str = (
        f'mssql+pyodbc://{username}:{password}@{server}/{database}?'
        f'driver={driver_name}&TrustServerCertificate=yes'
    )
    
    try:
        engine = create_engine(conn_str, pool_recycle=600, pool_pre_ping=True, pool_size=5, max_overflow=10)
        return engine
    except Exception as e:
        print(f"Error creando el motor de SQLAlchemy para {database}: {e}")
        return None
    
#############################################
##   VALIDACIÓN DE ACCESO (RECURSOS HH)    ##
#############################################

def validar_codigo_personal(codigo: str) -> tuple[bool, dict | None]:
    """
    Valida si el codigo_personal existe en la tabla origen.colaborador
    de la base de datos rpa_recursos_humanos ('RRHH').
    Retorna una tupla: (Existe: bool, Datos_Colaborador: dict o None)
    """
    # Limpieza básica: si no contiene dígitos o está vacío, rechazar de inmediato
    if not codigo or not codigo.strip().isdigit():
        return False, None

    # Forzamos la creación del motor apuntando a 'RRHH'
    engine = create_sqlalchemy_engine(db_type="RRHH")
    if engine is None:
        return False, None

    try:
        with engine.connect() as connection:
            # Consulta parametrizada utilizando text() para evitar SQL Injection
            query = text("""
                SELECT id, codigo_personal, documento, nombre, correo_corporativo, cargo 
                FROM origen.colaborador 
                WHERE activo = 1 and codigo_personal = :codigo
            """)
            
            result = connection.execute(query, {"codigo": int(codigo)}).fetchone()
            
            if result:
                # Retorna éxito junto con la estructura de datos del colaborador
                colaborador_data = {
                    "id": result.id,
                    "codigo_personal": result.codigo_personal,
                    "documento": result.documento,
                    "nombre": result.nombre,
                    "correo_corporativo": result.correo_corporativo,
                    "cargo": result.cargo
                }
                return True, colaborador_data
            
            return False, None

    except Exception as e:
        print(f"Error al validar el código personal en RRHH: {e}")
        return False, None
    finally:
        # Cerramos y liberamos los recursos del pool del motor RRHH
        if engine:
            engine.dispose()

#############################################
## DESCARGA DE DATOS DE SQL SERVER A EXCEL ##
#############################################

@st.cache_data
def fetch_data_to_excel(table_name=TARGET_TABLE):
    """
    Descarga todos los datos de la tabla de destino a un DataFrame.
    Crea y desecha el motor de SQLAlchemy en la llamada.
    """
    engine = create_sqlalchemy_engine()
    if engine is None:
        return None, "Error al crear el motor de base de datos."

    try:
        # El bloque 'with' asegura que connection.close() se llame al salir.
        with engine.connect() as connection:
            query = f"SELECT id,numero_maquina,fecha_offline,fecha_rt,sala,serie,fabricante,observaciones FROM {table_name}"      
            # FIX: Usar la conexión (connection) en lugar del motor (engine) en pd.read_sql
            df = pd.read_sql(query, connection) 
            if 'serie' in df.columns:
                df['serie'] = df['serie'].astype(str).replace(['None', 'nan', '<NA>'], None)

            return df, "Datos descargados correctamente."
        
    except Exception as e:
        return None, f"Error al descargar datos: {e}"
    finally:
        # Aseguramos que el motor se deseche al finalizar la operación de descarga.
        if engine:
            engine.dispose()

##########################################
## CARGA DE DATOS DE EXCEL A SQL SERVER ##
##########################################

def generate_merge_query(df: pd.DataFrame, table_name: str, id_column: str, temp_table_name: str) -> str:
    """
    Genera una consulta SQL MERGE dinámica para la operación Upsert.
    """
    updatable_cols = [col for col in df.columns if col != id_column]
    set_clauses = ", ".join([f"TARGET.[{col}] = SOURCE.[{col}]" for col in df.columns if col != id_column])
    insert_columns = ", ".join([f"[{col}]" for col in updatable_cols])
    insert_values = ", ".join([f"SOURCE.[{col}]" for col in updatable_cols])
    
    merge_sql = f"""
    MERGE INTO {table_name} AS TARGET
    USING (
        SELECT * FROM {temp_table_name}
    ) AS SOURCE ON (TARGET.[{id_column}] = SOURCE.[{id_column}])
    
    WHEN MATCHED THEN
        UPDATE SET
            {set_clauses}
            
    WHEN NOT MATCHED BY TARGET THEN
        INSERT ({insert_columns})
        VALUES ({insert_values});
    """
    return merge_sql

def run_upsert_process(df_excel: pd.DataFrame, engine):
    """
    Carga el DataFrame a una tabla temporal y ejecuta la sentencia MERGE.
    """
    # Usamos SQL_SERVER_CONFIG para verificar la disponibilidad de la configuración
    if df_excel.empty or not SQL_SERVER_CONFIG_GESTION or not all(SQL_SERVER_CONFIG_GESTION.values()):
        return False, "DataFrame vacío o configuración de BD no disponible. Revise el archivo Excel y secrets.toml."
        
    table_name = TARGET_TABLE
    id_column = KEY_COLUMN
    temp_table_name = "#TEMP_EXCEL_DATA" 

    try:
        # 'engine.begin()' inicia una transacción, asegurando el commit/rollback automático y utiliza una conexión del pool.
        with engine.begin() as connection:
            with warnings.catch_warnings():
                warnings.filterwarnings("ignore", message=".*is not found exactly as such in the database.*")
                
                # PASO 1: Asegurar limpieza previa de la tabla en la sesión actual de forma nativa
                connection.execute(text(f"IF OBJECT_ID('tempdb..{temp_table_name}') IS NOT NULL DROP TABLE {temp_table_name};"))
                
                # PASO 2: Crear la estructura enviando un DataFrame vacío (0 filas)
                # Usamos if_exists='append' para prohibirle a SQLAlchemy inspeccionar los metadatos del catálogo
                df_excel.head(0).to_sql(
                    name=temp_table_name, 
                    con=connection, 
                    if_exists='append', 
                    index=False
                ) 
                
                # PASO 3: Cargar los datos masivos reales mediante inserción directa
                df_excel.to_sql(
                    name=temp_table_name, 
                    con=connection, 
                    if_exists='append', 
                    index=False
                ) 
                
                # PASO 4: Generar dinámicamente y ejecutar la consulta MERGE
                merge_query = generate_merge_query(df_excel, table_name, id_column, temp_table_name) 
                connection.execute(text(merge_query))

                # PASO 5: Eliminar la tabla temporal manualmente al finalizar con éxito
                connection.execute(text(f"DROP TABLE {temp_table_name};"))
                
                # FIX: Retornar la tupla (bool, str) para el desempaquetado correcto en app.py
                return True, f"Proceso completado exitosamente"

    except Exception as e:
        # FIX: Retornar la tupla (bool, str) para el desempaquetado correcto en app.py
        return False, f"Error durante la ejecución del proceso ETL/MERGE: {e}"