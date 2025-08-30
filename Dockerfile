# Use Python 3.11 slim image
FROM python:3.11-slim

# Set maintainer information
LABEL maintainer="Govind Deshmukh <govind.ub47@gmail.com>"
LABEL description="ConfigLake - Centralized configuration and secrets management"
LABEL version="1.0.0"

# Set environment variables
ENV PYTHONUNBUFFERED=1
ENV PYTHONDONTWRITEBYTECODE=1
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Set work directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create directories for data persistence
RUN mkdir -p /app/instance /app/backups

# Create non-root user for security
RUN useradd -m -u 1000 configlake && \
    chown -R configlake:configlake /app
USER configlake

# Expose port
EXPOSE 5000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Default command
CMD ["python", "app.py"]