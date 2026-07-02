# =============================================================================
# Dockerfile multi-etapa para GestionDatos App (Streamlit + SQL Server)
# =============================================================================

# --- Parámetros de construcción ---
ARG PYTHON_VERSION=3.11-slim
ARG APP_PORT=8501
ARG STREAMLIT_HOME=/home/streamlituser

# =============================================================================
# FASE 1: Builder — Compila e instala dependencias Python
# =============================================================================
FROM python:${PYTHON_VERSION} AS builder

WORKDIR /build

# Instalar solo lo necesario para compilar ruedas nativas (pyodbc, etc.)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    unixodbc-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .

# Directorio de instalación controlado (evita depender de /root/.local)
ENV PYTHONUSERBASE=/deps
RUN pip install --no-cache-dir --user -r requirements.txt

# =============================================================================
# FASE 2: Runner — Imagen final, ligera y segura
# =============================================================================
FROM python:${PYTHON_VERSION} AS runner

ARG APP_PORT
ARG STREAMLIT_HOME
ENV APP_PORT=${APP_PORT:-8501}

WORKDIR /app

# ---------- Variables de entorno obligatorias (inyectar en timepo de ejecución) ----------
# DRIVER, SERVER, USER, PASSWORD, DATABASE_RRHH, DATABASE_GESTION
# Se leen via python-decouple desde variables de entorno del contenedor.
# ---------- Configuración de Python ----------
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUSERBASE=${STREAMLIT_HOME}/.local \
    PATH=${STREAMLIT_HOME}/.local/bin:$PATH

# ---------- Instalación del driver ODBC 18 para SQL Server ----------
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    ca-certificates \
    gnupg \
    unixodbc \
    && curl -fsSL https://packages.microsoft.com/keys/microsoft.asc \
       | gpg --dearmor -o /usr/share/keyrings/microsoft-prod.gpg \
    && echo "deb [arch=amd64,arm64 signed-by=/usr/share/keyrings/microsoft-prod.gpg] \
       https://packages.microsoft.com/debian/12/prod bookworm main" \
       > /etc/apt/sources.list.d/mssql-release.list \
    && apt-get update \
    && ACCEPT_EULA=Y apt-get install -y --no-install-recommends msodbcsql18 \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# ---------- Usuario no-root ----------
RUN useradd -m -u 1000 streamlituser

# ---------- Copia de artefactos ----------
COPY --from=builder --chown=streamlituser:streamlituser \
    /deps ${STREAMLIT_HOME}/.local

COPY --chown=streamlituser:streamlituser src/ .

# ---------- Puerto de escucha ----------
EXPOSE ${APP_PORT}

# ---------- Healthcheck ----------
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
    CMD curl --fail http://localhost:${APP_PORT}/_stcore/health || exit 1

# ---------- Señal de parada ----------
STOPSIGNAL SIGTERM

USER streamlituser

ENTRYPOINT ["streamlit", "run", "app.py"]
CMD ["--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]