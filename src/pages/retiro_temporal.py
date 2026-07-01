import streamlit as st
import pandas as pd
import io # Para manejo de archivos en memoria
from database.database_connector import create_sqlalchemy_engine, run_upsert_process, fetch_data_to_excel # Las importaciones de numpy y re han sido eliminadas ya que no se utilizan.
from config import KEY_COLUMN # Importar KEY_COLUMN directamente de config

@st.cache_resource
def get_cached_engine():
    return create_sqlalchemy_engine()

def cargar_descargar_retiro_temporal(usuario_sap):
    
    # --- PASO 1: INICIALIZAR SESSION STATE (CRÍTICO) ---
    if "uploader_key" not in st.session_state:
        st.session_state.uploader_key = 0

    ############################################
    ## CARGA DE ARCHIVO EXCEL PARA SQL SERVER ##
    ############################################

    st.header("1. Cargar y Sincronizar Datos")
    st.markdown("Sube un archivo Excel para actualizar o insertar registros en la base de datos")

    # Reemplazamos la llamada directa por la función con caché
    engine = get_cached_engine()

    if engine is None:
        # Mensaje de error ajustado para indicar la nueva sección [database]
        st.warning("Verifica que los drivers de ODBC estén instalados y las credenciales sean correctas.")
        return 

    # --- PASO 2: Pasamos la clave dinámica al componente ---
    uploaded_file = st.file_uploader(
        "Sube tu archivo Excel (.xlsx)", 
        type=["xlsx"],
        key=f"excel_uploader_{st.session_state.uploader_key}"  # <--- Descomentado y activo
    )

    if uploaded_file is not None:
        try:
            # Leer archivo a DataFrame y asegurar que los datos se leen como bytes para compatibilidad
            df_excel = pd.read_excel(
                io.BytesIO(uploaded_file.read())
            )
            
            # BUENA PRÁCTICA: Normalizar nombres de columnas (Quita espacios extras y pasa a minúsculas)
            # Esto evitará que "Observaciones" u "observaciones " fallen al compararse
            df_excel.columns = df_excel.columns.str.strip().str.lower()

            # Validación simple de columnas
            if KEY_COLUMN not in df_excel.columns:
                 # Usamos KEY_COLUMN directamente
                 st.error(f"Error de archivo: La columna de ID ('{KEY_COLUMN}') definida en 'config.py' no se encontró en el Excel.")
                 return
            
            # BUENA PRÁCTICA: Inyectar dinámicamente el usuario autenticado antes de enviar a la BD
            # Esto asegura la trazabilidad y auditoría sin depender de que venga en el Excel
            df_excel["usuario_sap_carga"] = int(usuario_sap)

            st.subheader("Vista Previa de Datos de Excel:")
            st.dataframe(df_excel.head())

            # Botón para ejecutar el proceso
            if st.button(f"Ejecutar Sincronización"):
                with st.spinner(f'Ejecutando Sincronizacion de excel con base de datos'):
                    # La función run_upsert_process gestiona la transacción y el cierre de conexión.
                    success, message = run_upsert_process(df_excel, engine)
                    
                    if success:
                        # 1. Limpiar caché de datos obligatoriamente
                        fetch_data_to_excel.clear()
                        
                        # 2. Modificar el key del uploader para "limpiar" el componente del archivo viejo
                        st.session_state.uploader_key += 1 
                        
                        # 3. Notificar éxito y forzar reinicio limpio
                        st.success(message)
                        st.rerun()
                    else:
                        st.error(f"Fallo del proceso: {message}")
                    
        except Exception as e:
            # Captura errores inesperados al procesar el archivo Excel.
            st.error(f"Error inesperado al procesar el archivo o la lógica: {e}")

    #####################################
    ## DESCARGA DE DATOS DE SQL SERVER ##
    #####################################
    
    st.header("2. Descargar Datos")
    st.markdown("Filtra y descarga el contenido actual de la tabla a un archivo Excel")
    
    # 1. Traer los datos (Gracias al @st.cache_data esto es súper rápido tras la primera carga)
    # Quitamos el st.button para la carga inicial así los filtros pueden leer los valores únicos disponibles.
    df_output, message = fetch_data_to_excel()
    
    if df_output is not None:
        # Asegurar formatos correctos para los filtros
        if 'fecha_offline' in df_output.columns:
            df_output['fecha_offline'] = pd.to_datetime(df_output['fecha_offline']).dt.date
            
        # --- SECCIÓN DE FILTROS ---
        st.subheader("Filtros de descarga")
        col1, col2 = st.columns(2)
        
        with col1:
            if 'fecha_offline' in df_output.columns and not df_output.empty:
                min_date = df_output['fecha_offline'].min()
                max_date = df_output['fecha_offline'].max()
                
                if pd.isnull(min_date): min_date = pd.Timestamp.now().date()
                if pd.isnull(max_date): max_date = pd.Timestamp.now().date()
                
                # Dinámico: Usar una clave única que cambie con el uploader_key para forzar su reinicio si los datos cambian
                date_range = st.date_input(
                    "Selecciona rango de Fecha Offline",
                    value=(min_date, max_date),
                    min_value=min_date,
                    max_value=max_date,
                    key=f"date_input_{st.session_state.uploader_key}" 
                )
            else:
                st.warning("Columna 'fecha_offline' no encontrada o tabla vacía.")
                date_range = None

        with col2:
            if 'sala' in df_output.columns and not df_output.empty:
                lista_salas = sorted(df_output['sala'].dropna().unique())
                selected_salas = st.multiselect(
                    "Selecciona las Salas",
                    options=lista_salas,
                    default=lista_salas,
                    key=f"sala_select_{st.session_state.uploader_key}" # Forzar reinicio de salas
                )
            else:
                st.warning("Columna 'sala' no encontrada o tabla vacía.")
                selected_salas = None

        # --- APLICAR FILTROS EN PANDAS ---
        df_filtrado = df_output.copy()
        
        if date_range and len(date_range) == 2:
            start_date, end_date = date_range
            df_filtrado = df_filtrado[
                (df_filtrado['fecha_offline'] >= start_date) & 
                (df_filtrado['fecha_offline'] <= end_date)
            ]
            
        if selected_salas is not None:
            df_filtrado = df_filtrado[df_filtrado['sala'].isin(selected_salas)]
            
        st.markdown(f"**Registros encontrados tras aplicar filtros:** {len(df_filtrado)}")
        st.dataframe(df_filtrado.head())
        
        if not df_filtrado.empty:
            excel_buffer = io.BytesIO()
            df_filtrado.to_excel(excel_buffer, index=False, engine='xlsxwriter')
            excel_buffer.seek(0)
            
            st.download_button(
                label="Descargar archivo",
                data=excel_buffer,
                file_name=f"export_{pd.Timestamp.now().strftime('%Y%m%d_%H%M%S')}.xlsx",
                mime="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                key="btn_download"
            )
        else:
            st.warning("No hay datos que coincidan con los filtros seleccionados.")
            
    else:
        st.error(f"Fallo al descargar los datos: {message}")
    
if __name__ == "__main__":
    cargar_descargar_retiro_temporal()