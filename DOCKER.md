# ConfigLake Docker Setup

This guide covers how to run ConfigLake using Docker.

## 🐳 Quick Start with Docker

### Option 1: Using Docker Compose (Recommended)

```bash
# Clone the repository
git clone https://github.com/Govind-Deshmukh/configlake.git
cd configlake

# Start with Docker Compose
docker-compose up -d

# Check logs
docker-compose logs -f configlake
```

### Option 2: Using Docker directly

```bash
# Build the image
docker build -t configlake .

# Run the container
docker run -d \
  --name configlake \
  -p 5000:5000 \
  -v configlake_data:/app/instance \
  -v configlake_backups:/app/backups \
  -e SECRET_KEY="your-secret-key" \
  configlake
```

### Option 3: Using pre-built image from Docker Hub

```bash
# Pull and run from Docker Hub
docker run -d \
  --name configlake \
  -p 5000:5000 \
  -v configlake_data:/app/instance \
  -v configlake_backups:/app/backups \
  -e SECRET_KEY="your-secret-key" \
  configlake/configlake:latest
```

## 🌐 Access the Application

Once running, access ConfigLake at: **http://localhost:5000**

## 🔧 Initial Setup

### 1. Create Admin User

```bash
# Enter the running container
docker exec -it configlake bash

# Run setup script
python setup.py

# Exit container
exit
```

### 2. Environment Variables

Create a `.env` file in your project directory:

```env
SECRET_KEY=your-very-secure-secret-key-change-this
FLASK_ENV=production
DB_PASSWORD=your-postgres-password-if-using-postgres
```

## 📦 Building and Pushing to Docker Hub

### 1. Build the Image

```bash
# Build with tag
docker build -t configlake/configlake:latest .

# Build with version tag
docker build -t configlake/configlake:v1.0.0 .
```

### 2. Test Locally

```bash
# Test the built image
docker run -d \
  --name configlake-test \
  -p 5000:5000 \
  configlake/configlake:latest

# Check if it's working
curl http://localhost:5000

# Cleanup test container
docker stop configlake-test
docker rm configlake-test
```

### 3. Push to Docker Hub

```bash
# Login to Docker Hub
docker login

# Push latest tag
docker push configlake/configlake:latest

# Push version tag
docker push configlake/configlake:v1.0.0
```

### 4. Multi-architecture Build (Optional)

```bash
# Create and use buildx builder
docker buildx create --name configlake-builder --use

# Build for multiple architectures
docker buildx build \
  --platform linux/amd64,linux/arm64 \
  -t configlake/configlake:latest \
  -t configlake/configlake:v1.0.0 \
  --push .
```

## 🗄️ Database Options

ConfigLake supports three database types configured via the `DATABASE_TYPE` environment variable.

### SQLite (Default)

```bash
# Default - no additional configuration needed
docker run -d \
  --name configlake \
  -p 5000:5000 \
  -e DATABASE_TYPE=sqlite \
  -v configlake_data:/app/instance \
  configlake/configlake:latest
```

### MySQL

```bash
# Using external MySQL
docker run -d \
  --name configlake \
  -p 5000:5000 \
  -e DATABASE_TYPE=mysql \
  -e MYSQL_USER=configlake \
  -e MYSQL_PASSWORD=secure_password \
  -e MYSQL_HOST=mysql_host \
  -e MYSQL_PORT=3306 \
  -e MYSQL_DB=configlake \
  -v configlake_data:/app/instance \
  configlake/configlake:latest
```

### PostgreSQL (Recommended for Production)

```bash
# Using external PostgreSQL
docker run -d \
  --name configlake \
  -p 5000:5000 \
  -e DATABASE_TYPE=postgresql \
  -e PG_USER=configlake \
  -e PG_PASSWORD=secure_password \
  -e PG_HOST=postgres_host \
  -e PG_PORT=5432 \
  -e PG_DB=configlake \
  -v configlake_data:/app/instance \
  configlake/configlake:latest

# Or uncomment PostgreSQL service in docker-compose.yml and use:
docker-compose up -d
```

## 🔍 Monitoring and Logs

```bash
# View logs
docker-compose logs -f configlake

# Check container health
docker-compose ps

# View resource usage
docker stats configlake
```

## 📂 Volume Management

### Backup Data

```bash
# Backup database
docker run --rm \
  -v configlake_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/configlake-backup.tar.gz -C /data .

# Backup with timestamp
docker run --rm \
  -v configlake_data:/data \
  -v $(pwd):/backup \
  alpine tar czf /backup/configlake-backup-$(date +%Y%m%d-%H%M%S).tar.gz -C /data .
```

### Restore Data

```bash
# Restore from backup
docker run --rm \
  -v configlake_data:/data \
  -v $(pwd):/backup \
  alpine tar xzf /backup/configlake-backup.tar.gz -C /data
```

## 🔒 Security Considerations

1. **Change default SECRET_KEY**: Always set a secure secret key
2. **Use HTTPS**: Deploy behind a reverse proxy with SSL
3. **Firewall**: Only expose port 5000 to trusted networks
4. **Regular backups**: Set up automated database backups
5. **Update regularly**: Keep the Docker image updated

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

## ❓ Troubleshooting

### Container won't start

```bash
# Check logs
docker logs configlake

# Check if port is available
netstat -tulpn | grep :5000
```

### Permission issues

```bash
# Fix volume permissions
docker exec -it configlake chown -R configlake:configlake /app/instance
```

### Database connection issues

```bash
# Check database connection
docker exec -it configlake python -c "from app import create_app, db; app=create_app(); app.app_context().push(); print('DB Connected:', db.engine.execute('SELECT 1').fetchone())"
```

## 📋 Docker Hub Repository

**Repository**: `configlake/configlake`  
**Tags**:

- `latest` - Latest stable version
- `v1.0.0` - Specific version
- `dev` - Development version

## 🤝 Contributing

To contribute to the Docker setup:

1. Fork the repository
2. Make your changes to Dockerfile or docker-compose.yml
3. Test locally with `docker-compose up --build`
4. Submit a pull request

## 📞 Support

- **Issues**: https://github.com/Govind-Deshmukh/configlake/issues
- **Discussions**: https://github.com/Govind-Deshmukh/configlake/discussions
- **Docker Hub**: https://hub.docker.com/r/configlake/configlake
