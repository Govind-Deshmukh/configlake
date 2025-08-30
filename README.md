# ConfigLake

A secure, centralized service for managing application configurations and sensitive secrets across multiple projects and environments.

## Features

- **Secure Secret Management**: All secrets are encrypted at rest using environment-specific keys
- **Multi-Environment Support**: Separate configurations for development, staging, production, etc.
- **Role-Based Access Control**: Owner, Maintainer, and Reader roles with granular permissions
- **IP Whitelisting**: Restrict access to specific IP addresses or ranges
- **API Token Authentication**: Secure programmatic access for applications
- **Backup & Restore**: Encrypted backups with password protection
- **Multiple Database Support**: SQLite, MySQL, or PostgreSQL

## Quick Start

### 1. Installation

```bash
# Clone the repository
git clone <repository-url>
cd config-manager

# Install dependencies
pip install -r requirements.txt

# Copy environment configuration
cp .env.example .env
```

### 2. Configuration

Edit the `.env` file with your settings:

```env
# Flask Configuration
SECRET_KEY=your-secret-key-here

# Database Configuration (choose one)
DATABASE_TYPE=sqlite  # Options: sqlite, mysql, postgresql

# For SQLite (default)
DATABASE_URL=sqlite:///config_manager.db

# For MySQL
MYSQL_USER=root
MYSQL_PASSWORD=password
MYSQL_HOST=localhost
MYSQL_PORT=3306
MYSQL_DB=config_manager

# For PostgreSQL
PG_USER=postgres
PG_PASSWORD=password
PG_HOST=localhost
PG_PORT=5432
PG_DB=config_manager

# Security
ENCRYPTION_KEY=generate-a-32-byte-key-for-production
ALLOWED_IPS=127.0.0.1,192.168.1.0/24
```

### 3. Database Setup

```bash
# Initialize the database
python app.py init-db

# Create an admin user
python app.py create-admin
```

### 4. Run the Application

```bash
python app.py
```

The application will be available at `http://localhost:5000`

## API Usage

### Authentication

All API requests require a Bearer token in the Authorization header:

```bash
Authorization: Bearer <your-api-token>
```

### Get Configurations

Retrieve all configurations for a specific environment:

```bash
GET /api/config/<project_id>/<environment_name>
```

Response:
```json
{
  "project_id": 1,
  "environment": "production",
  "configs": {
    "DATABASE_URL": "postgresql://...",
    "API_ENDPOINT": "https://api.example.com"
  }
}
```

### Get Secrets

Retrieve all encrypted secrets for a specific environment:

```bash
GET /api/secrets/<project_id>/<environment_name>
```

Response:
```json
{
  "project_id": 1,
  "environment": "production",
  "environment_key": "encryption-key-for-this-env",
  "secrets": {
    "API_KEY": "encrypted-value-1",
    "JWT_SECRET": "encrypted-value-2"
  }
}
```

### Get All Data

Retrieve both configurations and secrets:

```bash
GET /api/all/<project_id>/<environment_name>
```

### Client-Side Decryption

Secrets are returned encrypted. Decrypt them using the environment key:

```python
import base64
from cryptography.fernet import Fernet

def decrypt_secret(encrypted_value, environment_key):
    fernet = Fernet(environment_key.encode())
    decoded_value = base64.b64decode(encrypted_value.encode())
    return fernet.decrypt(decoded_value).decode()

# Usage
decrypted_secret = decrypt_secret(
    secrets['API_KEY'], 
    response['environment_key']
)
```

## Management API

### Create/Update Configuration

```bash
POST /api/manage/config/<project_id>/<environment_name>
Content-Type: application/json

{
  "key": "DATABASE_URL",
  "value": "postgresql://user:pass@localhost/db"
}
```

### Create/Update Secret

```bash
POST /api/manage/secret/<project_id>/<environment_name>
Content-Type: application/json

{
  "key": "API_KEY",
  "value": "secret-api-key-value"
}
```

### Delete Configuration/Secret

```bash
DELETE /api/manage/config/<project_id>/<environment_name>/<key>
DELETE /api/manage/secret/<project_id>/<environment_name>/<key>
```

### Generate API Token

```bash
POST /api/manage/token/<project_id>/<environment_id>
Content-Type: application/json

{
  "name": "Production API Token"
}
```

## Role Permissions

### Owner
- Full project control
- Manage users and roles
- Create/delete environments
- Backup and restore
- Security settings (IP whitelist)
- Generate API tokens

### Maintainer
- Create/update/delete configs and secrets
- View all project data
- Cannot manage users or security settings

### Reader
- View configurations and secrets
- Cannot make changes

## Security Features

### Encryption at Rest
- All secrets are encrypted using environment-specific keys
- Each environment has its own encryption key
- Keys are generated using Fernet (symmetric encryption)

### IP Whitelisting
- Restrict API access to specific IP addresses
- Support for both single IPs and CIDR ranges
- Configurable per project

### API Token Security
- Tokens are generated using cryptographically secure random functions
- Tokens can be scoped to specific projects and environments
- Configurable expiration times

### Backup Security
- Backups are encrypted using password-derived keys
- PBKDF2 with SHA-256 for key derivation
- ZIP compression with encrypted contents

## Example Client Implementation

### Python Client

```python
import requests
import base64
from cryptography.fernet import Fernet

class ConfigManager:
    def __init__(self, base_url, project_id, environment, api_token):
        self.base_url = base_url
        self.project_id = project_id
        self.environment = environment
        self.headers = {'Authorization': f'Bearer {api_token}'}
    
    def get_config(self, key=None):
        """Get configurations."""
        url = f"{self.base_url}/api/config/{self.project_id}/{self.environment}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        data = response.json()
        if key:
            return data['configs'].get(key)
        return data['configs']
    
    def get_secret(self, key):
        """Get and decrypt a secret."""
        url = f"{self.base_url}/api/all/{self.project_id}/{self.environment}"
        response = requests.get(url, headers=self.headers)
        response.raise_for_status()
        
        data = response.json()
        encrypted_value = data['secrets'].get(key)
        
        if not encrypted_value:
            return None
        
        # Decrypt the secret
        fernet = Fernet(data['environment_key'].encode())
        decoded_value = base64.b64decode(encrypted_value.encode())
        return fernet.decrypt(decoded_value).decode()

# Usage
config_manager = ConfigManager(
    base_url="https://config-manager.example.com",
    project_id=1,
    environment="production",
    api_token="your-api-token"
)

database_url = config_manager.get_config('DATABASE_URL')
api_key = config_manager.get_secret('API_KEY')
```

## Development

### Database Migrations

When making model changes:

1. Stop the application
2. Backup your data
3. Delete the database file (for SQLite)
4. Run `python app.py init-db`
5. Recreate your data or restore from backup

## Deployment

### Production Checklist

- [ ] Change default SECRET_KEY
- [ ] Generate secure ENCRYPTION_KEY
- [ ] Configure proper database (not SQLite for production)
- [ ] Set up HTTPS/TLS
- [ ] Configure IP whitelisting
- [ ] Set up regular backups
- [ ] Configure reverse proxy (nginx/Apache)
- [ ] Set appropriate file permissions
- [ ] Enable logging

### Docker Deployment

```dockerfile
FROM python:3.9-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install -r requirements.txt

COPY . .

EXPOSE 5000
CMD ["python", "app.py"]
```

## License

This project is licensed under the MIT License - see the LICENSE file for details.