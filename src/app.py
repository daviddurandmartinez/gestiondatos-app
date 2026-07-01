import os
import logging
import streamlit as st
from PIL import Image
from streamlit_option_menu import option_menu
from pages.retiro_temporal import cargar_descargar_retiro_temporal
from database.database_connector import validar_codigo_personal

# Imagenes en caché para realizar una sola subida
@st.cache_resource
def load_image(image_path):
    return Image.open(image_path)

def main():

    # En app.py, dentro de main(), donde inicializas el estado de la sesión:
    if "uploader_key" not in st.session_state:
        st.session_state["uploader_key"] = 0

    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    ruta_logo = os.path.join(BASE_DIR, "static", "images", "logo_newport.png")
    img = load_image(ruta_logo)

    # 1. Configuración obligatoria de la página (DEBE SER LO PRIMERO)
    st.set_page_config(
        page_title="Gestión de Datos",
        page_icon=img if img else "",
        layout="wide",
        initial_sidebar_state="expanded"
    )

    # 2. Inicializar variables de control de sesión
    if "autenticado" not in st.session_state:
        st.session_state["autenticado"] = False
    if "colaborador" not in st.session_state:
        st.session_state["colaborador"] = None

    # --- FLUJO DE CONTROL DE ACCESO (LOGIN) ---
    if not st.session_state["autenticado"]:
        # Modificamos temporalmente el layout visual para centrar el login
        col1, col2, col3, col4, col5 = st.columns([1, 1, 2,1,1])
        with col3:
            #if img:
            #    st.image(img, width=250)
            #st.title("Sistema de Gestión de Datos")
            st.subheader("Login")

            with st.form("form_login"):
                codigo_ingresado = st.text_input(
                    "Codigo SAP", 
                    placeholder="Ingrese su código de colaborador (ej: 1234)",
                    help="Código numérico que muestra en su fotocheck"
                ).strip()
                
                boton_ingresar = st.form_submit_button("Ingresar")

                if boton_ingresar:
                    if codigo_ingresado:
                        # Validar usando el motor 'RRHH' de tu database_connector
                        es_valido, datos = validar_codigo_personal(codigo_ingresado)
                        
                        if es_valido and datos:
                            st.session_state["autenticado"] = True
                            st.session_state["colaborador"] = datos
                            st.success(f"¡Bienvenido(a) {datos['nombre']}!")
                            st.rerun()  # Recarga la app con el nuevo estado
                        else:
                            st.error("El código ingresado no existe en los registros de Recursos Humanos.")
                    else:
                        st.warning("Por favor, digite su código personal.")
        return # Detiene la ejecución para que no pinte el menú lateral si no está logueado

    # --- FLUJO POST-LOGIN (APLICACIÓN PRINCIPAL) ---
    colaborador = st.session_state["colaborador"]

    # Crear el menú de navegación en la barra lateral (Sidebar)
    with st.sidebar:
        #if img:
        #    st.image(img, width='stretch')
        #    st.markdown("---")
        
        #st.markdown("###Usuario Activo")
        #st.caption(f"\n{colaborador['nombre']}")
        #st.caption(f"{colaborador['codigo_personal']}")
        #st.markdown("---")

        seleccion = option_menu(
            menu_title="Menú",
            options=["Inicio", "Retiro Temporal"],
            icons=["house", "clock-history"], 
            menu_icon="cast",
            default_index=0,
        )
        
        st.markdown("---")
        ##st.markdown("### Usuario Activo")
        ##st.caption(f"\n{colaborador['nombre']}")
        ##st.caption(f"{colaborador['codigo_personal']}")
        
        # Botón para salir de la aplicación de forma segura
        if st.button("Cerrar Sesion", use_container_width=True):
            st.session_state["autenticado"] = False
            st.session_state["colaborador"] = None
            st.rerun()

    # Lógica de enrutamiento basada en la selección del menú
    if seleccion == "Inicio":
        st.title("Bienvenido al sistema de Gestión de Datos")
        st.markdown(f"Hola {colaborador['nombre']}, has ingresado correctamente al sistema.")
        st.markdown("Seleccione una opción del menú lateral para comenzar a operar.")
    elif seleccion == "Retiro Temporal":
        # Extraemos de forma segura el código personal del colaborador logueado
        codigo_usuario = colaborador.get('codigo_personal')
        # Pasamos el código como argumento a la vista correspondiente
        cargar_descargar_retiro_temporal(usuario_sap=codigo_usuario)

# Silenciar los mensajes ruidosos de conexiones perdidas en asyncio
logging.getLogger("asyncio").setLevel(logging.CRITICAL)

if __name__ == "__main__":
    main()