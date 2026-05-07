# ==============================================================================
# Topshop Amazon System — imagem para Railway
# ==============================================================================
# Build: docker build -t criar-planilhas .
# Run local: docker run -p 8080:8080 --env-file .env -v $(pwd)/data:/data criar-planilhas
# ==============================================================================

FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PORT=8080 \
    DATA_DIR=/data \
    APP_CONFIG_PATH=/data/app_config.json \
    ENV=production

WORKDIR /app

# Dependências de sistema:
#   - build-essential + libpq-dev para psycopg (caso a wheel binária falhe)
#   - curl para healthcheck
#   - locales para suportar nomes de arquivo com acentos (DESCRIÇÃO.xlsx)
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        curl \
        locales \
    && sed -i '/pt_BR.UTF-8/s/^# //' /etc/locale.gen \
    && locale-gen \
    && rm -rf /var/lib/apt/lists/*

ENV LANG=pt_BR.UTF-8 \
    LC_ALL=pt_BR.UTF-8

# Instala deps Python primeiro (camada cacheável)
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Copia o código
COPY . .

# Garante permissão de execução do entrypoint
RUN chmod +x /app/start.sh

# Diretório de dados (ponto de montagem do Volume Railway)
RUN mkdir -p /data

EXPOSE 8080

CMD ["/app/start.sh"]
