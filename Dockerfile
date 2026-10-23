FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV PIP_NO_CACHE_DIR=1

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install -r requirements.txt

# Copy application
COPY . .

# Create non-root user
RUN useradd -m -u 1000 tizahab && \
    chown -R tizahab:tizahab /app && \
    mkdir -p /app/logs && \
    mkdir -p /app/staticfiles && \
    chown -R tizahab:tizahab /app/logs /app/staticfiles

USER tizahab

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=5s --retries=3 \
    CMD python -c "import os, urllib.request; host=os.environ['DJANGO_ALLOWED_HOSTS'].split(',')[0].strip(); request=urllib.request.Request('http://127.0.0.1:8000/login/', headers={'Host':host, 'X-Forwarded-Proto':'https'}); urllib.request.urlopen(request, timeout=5).read()"

# Expose port
EXPOSE 8000

# Copy and wire entrypoint (migrate + collectstatic + gunicorn at runtime)
COPY --chown=tizahab:tizahab entrypoint.sh /entrypoint.sh
RUN chmod +x /entrypoint.sh
ENTRYPOINT ["/entrypoint.sh"]
