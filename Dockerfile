FROM python:3.12-slim

LABEL maintainer="Govind Deshmukh <govind.ub47@gmail.com>"
LABEL description="ConfigLake - Self-hosted secrets and configuration manager"
LABEL version="1.0.1"

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_APP=app.py
# Never enable debug in the image — callers can override if truly needed
ENV FLASK_DEBUG=0

WORKDIR /app

# curl is needed for the HEALTHCHECK; gcc for any C-extension wheels
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

# Directories the app writes to at runtime
RUN mkdir -p /app/instance /app/backups /app/certs

RUN chmod +x startup.sh

# Non-root user — created before chown so the layer is minimal
RUN useradd -m -u 1000 configlake && \
    chown -R configlake:configlake /app

USER configlake

# 5000 = HTTP / Flask dev server
# 443  = HTTPS when SSL_MODE=self-signed or manual
EXPOSE 5000 443

# HEAD /auth/login avoids the redirect on / and doesn't require auth
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -fsk http://localhost:5000/auth/login || exit 1

CMD ["./startup.sh"]
