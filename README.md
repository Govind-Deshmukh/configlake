# ConfigLake

A secure, centralized configuration and secrets management platform for modern applications. ConfigLake helps you organize your environment variables, API keys, database connections, and other sensitive data across different environments (development, staging, production) in one secure dashboard.

## What is ConfigLake?

ConfigLake is a Python-based middleware that provides a web dashboard and API for managing application configurations and secrets. Instead of scattered `.env` files or hardcoded values, ConfigLake gives you:

- **One central place** to manage all your app configs
- **Secure encryption** for sensitive data like passwords and API keys  
- **Multiple environments** support (dev, staging, prod)
- **Easy access** via Python and Node.js client libraries
- **Team collaboration** with role-based permissions

## Features

- **Secure Secret Management**: All secrets are encrypted at rest using environment-specific keys
- **Multi-Environment Support**: Separate configurations for development, staging, production, etc.
- **Role-Based Access Control**: Owner, Maintainer, and Reader roles with granular permissions
- **IP Whitelisting**: Restrict access to specific IP addresses or ranges
- **API Token Authentication**: Secure programmatic access for applications
- **Backup & Restore**: Encrypted backups with password protection
- **Multiple Database Support**: SQLite, MySQL, or PostgreSQL

## Quick Start

### Option 1: Using Docker (Recommended)

The easiest way to get started:

```bash
# Pull and run ConfigLake
docker pull configlake/configlake
docker run -d --name configlake -p 5000:5000 configlake/configlake

# Create admin user
docker exec -it configlake python app.py create-admin

# Access at http://localhost:5000
```

### Option 2: Manual Installation

```bash
# Clone the repository  
git clone https://github.com/Govind-Deshmukh/configlake
cd configlake

# Install dependencies
pip install -r requirements.txt

# Setup database and admin user
python app.py init-db
python app.py create-admin

# Run the application
python app.py
```

Visit `http://localhost:5000` and login with your admin credentials.

## Client Libraries

ConfigLake provides official client libraries for easy integration:

### Python Client

```bash
pip install configlake
```

```python
from configlake import getConfig, getSecrets, getAllDetails

# Get configurations only
configs = getConfig("http://localhost:5000", "your-token", 1, "production")
db_url = configs["DATABASE_URL"]

# Get secrets only (automatically decrypted)
secrets = getSecrets("http://localhost:5000", "your-token", 1, "production")
api_key = secrets["API_KEY"]

# Get everything together
data = getAllDetails("http://localhost:5000", "your-token", 1, "production")
```

### Node.js Client

```bash
npm install configlake
```

```javascript
import { getConfig, getSecrets, getAllDetails } from 'configlake';

// Get configurations only
const configs = await getConfig("http://localhost:5000", "your-token", 1, "production");
const dbUrl = configs.DATABASE_URL;

// Get secrets only (automatically decrypted)
const secrets = await getSecrets("http://localhost:5000", "your-token", 1, "production");
const apiKey = secrets.API_KEY;

// Get everything together
const data = await getAllDetails("http://localhost:5000", "your-token", 1, "production");
```

## Direct API Access

If you prefer direct API calls:

### Get Data
```bash
# Get configs and secrets
curl -H "Authorization: Bearer YOUR_TOKEN" \
  http://localhost:5000/api/all/PROJECT_ID/ENVIRONMENT
```

### Manage Data
```bash  
# Add/update config
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"DATABASE_URL","value":"postgresql://..."}' \
  http://localhost:5000/api/manage/config/PROJECT_ID/ENVIRONMENT

# Add/update secret
curl -X POST -H "Authorization: Bearer YOUR_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"key":"API_KEY","value":"secret-value"}' \
  http://localhost:5000/api/manage/secret/PROJECT_ID/ENVIRONMENT
```

## User Roles

ConfigLake has three user roles for team collaboration:

- **Owner**: Full access - manage users, projects, security settings
- **Maintainer**: Can create/edit/delete configs and secrets  
- **Reader**: View-only access to configurations and secrets

## Security Features

- **Encryption at Rest**: Secrets are encrypted using environment-specific keys
- **IP Whitelisting**: Restrict API access to specific IP addresses
- **API Token Authentication**: Secure token-based authentication
- **Role-Based Access**: Control what users can see and modify
- **Secure Backups**: Encrypted backup system with password protection

## Database Support

ConfigLake works with multiple database types:

- **SQLite** (default): Perfect for getting started, no setup required
- **PostgreSQL** (recommended for production): Best performance and features
- **MySQL**: Alternative production database option

### Database Configuration

Set your database type using environment variables:

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

## Docker Deployment

ConfigLake is available as a Docker image for easy deployment:

### Basic Docker Run

```bash
# Run with default SQLite database
docker run -d \
  --name configlake \
  -p 5000:5000 \
  -v configlake_data:/app/instance \
  -e SECRET_KEY="your-secret-key" \
  configlake/configlake

# Create admin user
docker exec -it configlake python app.py create-admin
```

### Docker Compose (Recommended)

Create a `docker-compose.yml` file:

```yaml
version: '3.8'
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
  configlake_backups:
  postgres_data:
```

Run with: `docker-compose up -d`

## Getting Started Guide

### 1. Set Up ConfigLake
Choose your preferred method:
- **Docker**: `docker run configlake/configlake` (easiest)
- **Manual**: Clone repository and run `python app.py`

### 2. Access the Dashboard  
Open `http://localhost:5000` and login with admin credentials.

### 3. Create Your First Project
1. Click "Create Project" 
2. Add environments (development, staging, production)
3. Add team members with appropriate roles

### 4. Add Configuration Data
- **Configs**: Non-sensitive settings (database URLs, API endpoints)
- **Secrets**: Sensitive data (passwords, API keys) - automatically encrypted

### 5. Generate API Token
Create tokens for your applications to access the data programmatically.

### 6. Integrate with Your App
Install the client library and fetch your configuration:

```python
# Python
from configlake import getAllDetails
data = getAllDetails("http://localhost:5000", "token", project_id, "production")
```

```javascript
// Node.js  
import { getAllDetails } from 'configlake';
const data = await getAllDetails("http://localhost:5000", "token", projectId, "production");
```

## Production Deployment

For production use:
1. Use PostgreSQL or MySQL database (not SQLite)
2. Set strong `SECRET_KEY` and `ENCRYPTION_KEY`
3. Enable HTTPS with reverse proxy (nginx/Apache)
4. Configure IP whitelisting for security
5. Set up regular backups

## Support & Links

- **Docker Image**: `docker pull configlake/configlake`
- **Python Package**: `pip install configlake`
- **NPM Package**: `npm install configlake`
- **GitHub Issues**: Report bugs and feature requests
- **Documentation**: See [DOCKER.md](./DOCKER.md) for detailed Docker instructions

## License

MIT License - see LICENSE file for details.