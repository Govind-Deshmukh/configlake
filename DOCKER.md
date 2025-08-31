# ConfigLake Docker Guide

Complete guide for running ConfigLake using Docker - the easiest way to deploy your configuration and secrets management platform.

## What is ConfigLake?

ConfigLake is a centralized platform for managing application configurations and secrets across different environments. With Docker, you can have it running in minutes!

## Quick Start (30 seconds!)

The fastest way to get ConfigLake running:

```bash
# Pull and run ConfigLake
docker pull configlake/configlake
docker run -d --name configlake -p 5000:5000 configlake/configlake

# Create your admin user
docker exec -it configlake python app.py create-admin

# Access at http://localhost:5000
```

Done! ConfigLake is now running on your machine.

## Installation Options

### Option 1: Pre-built Image (Recommended)

Use the official image from Docker Hub:

```bash
# Basic setup with SQLite database
docker run -d \
  --name configlake \
  -p 5000:5000 \
  -v configlake_data:/app/instance \
  -v configlake_backups:/app/backups \
  -e SECRET_KEY="change-this-in-production" \
  configlake/configlake:latest

# Create admin user
docker exec -it configlake python app.py create-admin
```

### Option 2: Docker Compose (Best for Production)

Create a `docker-compose.yml` file:

```yaml
version: "3.8"
services:
  configlake:
    image: configlake/configlake:latest
    ports:
      - "5000:5000"
    volumes:
      - configlake_data:/app/instance
      - configlake_backups:/app/backups
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_TYPE=sqlite
    restart: unless-stopped

volumes:
  configlake_data:
  configlake_backups:
```

Run with:

```bash
# Set your secret key
export SECRET_KEY="your-super-secure-secret-key-here"

# Start ConfigLake
docker-compose up -d

# Create admin user
docker-compose exec configlake python app.py create-admin
```

### Option 3: Build from Source

```bash
# Clone and build
git clone https://github.com/Govind-Deshmukh/configlake
cd configlake
docker build -t my-configlake .

# Run your custom build
docker run -d --name configlake -p 5000:5000 my-configlake
```

## First Time Setup

### 1. Access ConfigLake

Open your browser and go to: **http://localhost:5000**

### 2. Create Admin User

```bash
# Create your admin account
docker exec -it configlake python app.py create-admin

# Follow the prompts to enter:
# - Username
# - Email
# - Password
```

### 3. Login and Start Using

- Login with your admin credentials
- Create your first project
- Add environments (development, staging, production)
- Start adding your configuration data!

## Database Options

ConfigLake supports different databases based on your needs:

### SQLite (Default - Perfect for Getting Started)

```bash
# No additional setup required!
docker run -d --name configlake -p 5000:5000 configlake/configlake
```

### PostgreSQL (Recommended for Production)

```yaml
# docker-compose.yml
version: "3.8"
services:
  configlake:
    image: configlake/configlake:latest
    ports:
      - "5000:5000"
    volumes:
      - configlake_data:/app/instance
    environment:
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_TYPE=postgresql
      - PG_HOST=postgres
      - PG_USER=configlake
      - PG_PASSWORD=${DB_PASSWORD}
      - PG_DB=configlake
    depends_on:
      - postgres

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: configlake
      POSTGRES_USER: configlake
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data

volumes:
  configlake_data:
  postgres_data:
```

### MySQL

```yaml
# Add to your docker-compose.yml
services:
  configlake:
    environment:
      - DATABASE_TYPE=mysql
      - MYSQL_HOST=mysql
      - MYSQL_USER=configlake
      - MYSQL_PASSWORD=${DB_PASSWORD}
      - MYSQL_DB=configlake

  mysql:
    image: mysql:8
    environment:
      MYSQL_DATABASE: configlake
      MYSQL_USER: configlake
      MYSQL_PASSWORD: ${DB_PASSWORD}
      MYSQL_ROOT_PASSWORD: ${DB_PASSWORD}
```

## Using with Your Applications

Once ConfigLake is running, integrate it with your applications:

### Python Applications

```bash
# Install the client library
pip install configlake
```

```python
from configlake import getAllDetails

# Load configuration
config = getAllDetails(
    "http://localhost:5000",  # ConfigLake URL
    "your-api-token",        # Generate in dashboard
    1,                       # Project ID
    "production"             # Environment
)

# Use in your app
database_url = config["configs"]["DATABASE_URL"]
api_key = config["secrets"]["API_KEY"]
```

### Node.js Applications

```bash
# Install the client library
npm install configlake
```

```javascript
import { getAllDetails } from "configlake";

// Load configuration
const config = await getAllDetails(
  "http://localhost:5000", // ConfigLake URL
  "your-api-token", // Generate in dashboard
  1, // Project ID
  "production" // Environment
);

// Use in your app
const databaseUrl = config.configs.DATABASE_URL;
const apiKey = config.secrets.API_KEY;
```

## Environment Variables

Configure ConfigLake using these environment variables:

### Basic Configuration

```bash
# Required
SECRET_KEY=your-super-secure-secret-key-change-in-production

# Optional
FLASK_ENV=production
PORT=5000
```

### Database Configuration

```bash
# SQLite (default)
DATABASE_TYPE=sqlite

# PostgreSQL
DATABASE_TYPE=postgresql
PG_HOST=localhost
PG_PORT=5432
PG_USER=configlake
PG_PASSWORD=your_password
PG_DB=configlake

# MySQL
DATABASE_TYPE=mysql
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_USER=configlake
MYSQL_PASSWORD=your_password
MYSQL_DB=configlake
```

### Security Configuration

```bash
# Encryption key for secrets (32 bytes)
ENCRYPTION_KEY=your-32-byte-encryption-key-here

# IP whitelisting (comma-separated)
ALLOWED_IPS=127.0.0.1,192.168.1.0/24,10.0.0.0/8

# API token expiry in seconds
API_TOKEN_EXPIRY=86400
```

## Production Deployment

### Docker Compose with PostgreSQL (Recommended)

Create a production-ready setup:

```yaml
# docker-compose.prod.yml
version: "3.8"

services:
  configlake:
    image: configlake/configlake:latest
    ports:
      - "5000:5000"
    volumes:
      - configlake_data:/app/instance
      - configlake_backups:/app/backups
    environment:
      - FLASK_ENV=production
      - SECRET_KEY=${SECRET_KEY}
      - DATABASE_TYPE=postgresql
      - PG_HOST=postgres
      - PG_USER=configlake
      - PG_PASSWORD=${DB_PASSWORD}
      - PG_DB=configlake
      - ENCRYPTION_KEY=${ENCRYPTION_KEY}
      - ALLOWED_IPS=${ALLOWED_IPS}
    depends_on:
      - postgres
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:5000/"]
      interval: 30s
      timeout: 10s
      retries: 3

  postgres:
    image: postgres:15-alpine
    environment:
      POSTGRES_DB: configlake
      POSTGRES_USER: configlake
      POSTGRES_PASSWORD: ${DB_PASSWORD}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    restart: unless-stopped

  # Optional: Add nginx reverse proxy
  nginx:
    image: nginx:alpine
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf
      - ./ssl:/etc/nginx/ssl
    depends_on:
      - configlake
    restart: unless-stopped

volumes:
  configlake_data:
  configlake_backups:
  postgres_data:
```

### Environment File for Production

```bash
# .env.prod
SECRET_KEY=your-super-secure-secret-key-at-least-32-characters-long
DB_PASSWORD=secure-database-password-here
ENCRYPTION_KEY=your-32-byte-encryption-key-for-secrets-storage
ALLOWED_IPS=192.168.1.0/24,10.0.0.0/8
```

### Deploy to Production

```bash
# Load environment variables
source .env.prod

# Deploy
docker-compose -f docker-compose.prod.yml up -d

# Create admin user
docker-compose -f docker-compose.prod.yml exec configlake python app.py create-admin

# Check status
docker-compose -f docker-compose.prod.yml ps
```

## Management and Maintenance

### Monitor Your ConfigLake Instance

```bash
# View application logs
docker-compose logs -f configlake

# Check all services status
docker-compose ps

# Monitor resource usage
docker stats configlake

# View database logs (if using PostgreSQL)
docker-compose logs postgres
```

### Backup Your Data

**Automatic Backup (Recommended):**

```bash
# Create a backup script
cat > backup-configlake.sh << 'EOF'
#!/bin/bash
BACKUP_DIR="/backups/configlake"
DATE=$(date +%Y%m%d-%H%M%S)
mkdir -p $BACKUP_DIR

# Backup application data
docker run --rm \
  -v configlake_data:/data \
  -v $BACKUP_DIR:/backup \
  alpine tar czf /backup/configlake-data-$DATE.tar.gz -C /data .

# Backup database (if PostgreSQL)
docker-compose exec -T postgres pg_dump -U configlake configlake > $BACKUP_DIR/configlake-db-$DATE.sql

echo "Backup completed: $BACKUP_DIR"
EOF

chmod +x backup-configlake.sh

# Run backup
./backup-configlake.sh

# Add to crontab for daily backups
echo "0 2 * * * /path/to/backup-configlake.sh" | crontab -
```

**Manual Backup:**

```bash
# Backup data volume
docker run --rm \
  -v configlake_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/configlake-backup-$(date +%Y%m%d).tar.gz -C /data .
```

### Restore From Backup

```bash
# Stop ConfigLake
docker-compose down

# Restore data
docker run --rm \
  -v configlake_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/configlake-backup-20240101.tar.gz -C /data

# Start ConfigLake
docker-compose up -d
```

### Update ConfigLake

```bash
# Pull latest image
docker pull configlake/configlake:latest

# Restart with new image
docker-compose down
docker-compose up -d

# Verify update
docker-compose logs configlake
```

## 🚀 Production Deployment

### Using Docker Compose with Traefik (Recommended)

```yaml
version: '3.8'

services:
  configlake:
    image: configlake/configlake:latest
    container_name: configlake
    volumes:
      - configlake_data:/app/instance
      - configlake_backups:/app/backups
    environment:
      - FLASK_ENV=production
      - SECRET_KEY=${SECRET_KEY}
    labels:
      - "traefik.enable=true"
      - "traefik.http.routers.configlake.rule=Host(\`configlake.yourdomain.com\`)"
      - "traefik.http.routers.configlake.tls.certresolver=letsencrypt"
    networks:
      - web
    restart: unless-stopped

networks:
  web:
    external: true

volumes:
  configlake_data:
  configlake_backups:
```

### Environment Variables for Production

```env
# Flask Configuration
SECRET_KEY=your-super-secure-random-key-here-at-least-32-characters
FLASK_ENV=production

# Database Configuration
DATABASE_TYPE=postgresql
PG_USER=configlake
PG_PASSWORD=secure_password
PG_HOST=postgres_host
PG_PORT=5432
PG_DB=configlake

# Security Configuration
ENCRYPTION_KEY=your-32-byte-encryption-key-for-secrets
ALLOWED_IPS=192.168.1.0/24,10.0.0.0/8
API_TOKEN_EXPIRY=86400

# Optional: MySQL Configuration (if using MySQL)
# DATABASE_TYPE=mysql
# MYSQL_USER=configlake
# MYSQL_PASSWORD=secure_password
# MYSQL_HOST=mysql_host
# MYSQL_PORT=3306
# MYSQL_DB=configlake
```

## 🛠️ Development

### Development Setup with Hot Reload

```yaml
version: "3.8"

services:
  configlake-dev:
    build:
      context: .
      dockerfile: Dockerfile
    ports:
      - "5000:5000"
    volumes:
      - .:/app
      - configlake_dev_data:/app/instance
    environment:
      - FLASK_ENV=development
      - FLASK_DEBUG=1
    command: python app.py
```

## Troubleshooting

### Common Issues and Solutions

**ConfigLake won't start:**

```bash
# Check logs for errors
docker-compose logs configlake

# Common fixes:
# 1. Make sure port 5000 is available
sudo netstat -tlnp | grep :5000

# 2. Check if SECRET_KEY is set
docker-compose exec configlake env | grep SECRET_KEY

# 3. Verify database connection (if using external DB)
docker-compose exec configlake python -c "from app import create_app, db; app=create_app(); print('DB OK')"
```

**Can't create admin user:**

```bash
# Make sure ConfigLake is running first
docker-compose ps

# Try interactive mode
docker-compose exec configlake python app.py create-admin

# Or enter the container manually
docker-compose exec configlake bash
python app.py create-admin
```

**Database connection issues:**

```bash
# Check database container status
docker-compose ps postgres

# Check database logs
docker-compose logs postgres

# Test database connection
docker-compose exec postgres psql -U configlake -d configlake -c "\dt"
```

**Permission issues:**

```bash
# Fix volume permissions
docker-compose exec configlake chown -R configlake:configlake /app/instance /app/backups
```

### Performance Tuning

**For High Traffic:**

```yaml
# docker-compose.yml - Add resource limits
services:
  configlake:
    image: configlake/configlake:latest
    deploy:
      resources:
        limits:
          memory: 1G
          cpus: "0.5"
        reservations:
          memory: 512M
          cpus: "0.25"
    environment:
      - FLASK_ENV=production
      - WORKERS=4 # Adjust based on CPU cores
```

**Database Optimization:**

```yaml
# For PostgreSQL
postgres:
  image: postgres:15-alpine
  command: >
    postgres
    -c max_connections=100
    -c shared_buffers=256MB
    -c effective_cache_size=1GB
    -c maintenance_work_mem=64MB
```

## Quick Reference

### Essential Commands

```bash
# Start ConfigLake
docker-compose up -d

# View logs
docker-compose logs -f configlake

# Create admin user
docker-compose exec configlake python app.py create-admin

# Backup data
docker-compose exec postgres pg_dump -U configlake configlake > backup.sql

# Update ConfigLake
docker-compose pull && docker-compose up -d

# Stop ConfigLake
docker-compose down
```

### Links and Resources

- **Docker Image**: `docker pull configlake/configlake`
- **GitHub Repository**: https://github.com/Govind-Deshmukh/configlake
- **Python Client**: `pip install configlake`
- **Node.js Client**: `npm install configlake`
- **Issues**: https://github.com/Govind-Deshmukh/configlake/issues

## License

MIT License - see the main repository for details.
