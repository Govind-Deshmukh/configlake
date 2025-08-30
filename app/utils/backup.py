import json
import zipfile
import io
from datetime import datetime
from flask import current_app
from app import db
from app.models import Project, Environment, Config, Secret, ProjectUser, AllowedIP, User
from app.utils.encryption import EncryptionManager

class BackupManager:
    @staticmethod
    def create_project_backup(project_id, include_users=True):
        """Create a complete backup of a project."""
        project = Project.query.get(project_id)
        if not project:
            raise ValueError("Project not found")
        
        backup_data = {
            'version': '1.0',
            'created_at': datetime.utcnow().isoformat(),
            'project': {
                'name': project.name,
                'description': project.description,
                'created_at': project.created_at.isoformat()
            },
            'environments': [],
            'users': [] if include_users else None,
            'allowed_ips': []
        }
        
        # Backup environments with their configs and secrets
        environments = Environment.query.filter_by(project_id=project_id).all()
        for env in environments:
            env_data = {
                'name': env.name,
                'secret_key': env.secret_key,
                'created_at': env.created_at.isoformat(),
                'configs': [],
                'secrets': []
            }
            
            # Backup configs
            configs = Config.query.filter_by(environment_id=env.id).all()
            for config in configs:
                env_data['configs'].append({
                    'key': config.key,
                    'value': config.value,
                    'created_at': config.created_at.isoformat(),
                    'updated_at': config.updated_at.isoformat()
                })
            
            # Backup secrets (keep encrypted)
            secrets = Secret.query.filter_by(environment_id=env.id).all()
            for secret in secrets:
                env_data['secrets'].append({
                    'key': secret.key,
                    'encrypted_value': secret.encrypted_value,
                    'created_at': secret.created_at.isoformat(),
                    'updated_at': secret.updated_at.isoformat()
                })
            
            backup_data['environments'].append(env_data)
        
        # Backup project users (if requested)
        if include_users:
            project_users = ProjectUser.query.filter_by(project_id=project_id).all()
            for pu in project_users:
                user = User.query.get(pu.user_id)
                backup_data['users'].append({
                    'username': user.username,
                    'email': user.email,
                    'role': pu.role,
                    'created_at': pu.created_at.isoformat()
                })
        
        # Backup allowed IPs
        allowed_ips = AllowedIP.query.filter_by(project_id=project_id).all()
        for ip in allowed_ips:
            backup_data['allowed_ips'].append({
                'ip_address': ip.ip_address,
                'description': ip.description,
                'created_at': ip.created_at.isoformat()
            })
        
        return backup_data
    
    @staticmethod
    def create_encrypted_backup(project_id, password, include_users=True):
        """Create an encrypted backup of a project."""
        backup_data = BackupManager.create_project_backup(project_id, include_users)
        
        # Convert to JSON string
        json_data = json.dumps(backup_data, indent=2)
        
        # Encrypt the backup
        key, salt = EncryptionManager.derive_key_from_password(password)
        encrypted_backup = EncryptionManager.encrypt_value(json_data, key)
        
        # Create a ZIP file with the encrypted backup and salt
        zip_buffer = io.BytesIO()
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            zip_file.writestr('backup.encrypted', encrypted_backup)
            zip_file.writestr('salt', salt.hex())
            zip_file.writestr('info.json', json.dumps({
                'version': '1.0',
                'encrypted': True,
                'created_at': datetime.utcnow().isoformat()
            }))
        
        zip_buffer.seek(0)
        return zip_buffer.getvalue()
    
    @staticmethod
    def restore_project_backup(backup_data, new_project_name=None, restore_users=False):
        """Restore a project from backup data."""
        try:
            # Validate backup format
            if 'version' not in backup_data or 'project' not in backup_data:
                raise ValueError("Invalid backup format")
            
            project_name = new_project_name or backup_data['project']['name']
            
            # Check if project name already exists
            existing_project = Project.query.filter_by(name=project_name).first()
            if existing_project:
                raise ValueError(f"Project '{project_name}' already exists")
            
            # Create new project
            project = Project(
                name=project_name,
                description=backup_data['project']['description']
            )
            db.session.add(project)
            db.session.flush()  # Get project ID
            
            # Restore environments
            for env_data in backup_data.get('environments', []):
                environment = Environment(
                    name=env_data['name'],
                    project_id=project.id,
                    secret_key=env_data['secret_key']
                )
                db.session.add(environment)
                db.session.flush()  # Get environment ID
                
                # Restore configs
                for config_data in env_data.get('configs', []):
                    config = Config(
                        key=config_data['key'],
                        value=config_data['value'],
                        environment_id=environment.id
                    )
                    db.session.add(config)
                
                # Restore secrets
                for secret_data in env_data.get('secrets', []):
                    secret = Secret(
                        key=secret_data['key'],
                        encrypted_value=secret_data['encrypted_value'],
                        environment_id=environment.id
                    )
                    db.session.add(secret)
            
            # Restore users (if requested and available)
            if restore_users and backup_data.get('users'):
                for user_data in backup_data['users']:
                    # Find existing user by username or email
                    user = User.query.filter(
                        (User.username == user_data['username']) | 
                        (User.email == user_data['email'])
                    ).first()
                    
                    if user:
                        # Add user to project
                        project_user = ProjectUser(
                            user_id=user.id,
                            project_id=project.id,
                            role=user_data['role']
                        )
                        db.session.add(project_user)
            
            # Restore allowed IPs
            for ip_data in backup_data.get('allowed_ips', []):
                allowed_ip = AllowedIP(
                    ip_address=ip_data['ip_address'],
                    project_id=project.id,
                    description=ip_data['description']
                )
                db.session.add(allowed_ip)
            
            db.session.commit()
            return project
            
        except Exception as e:
            db.session.rollback()
            raise e
    
    @staticmethod
    def restore_encrypted_backup(zip_data, password, new_project_name=None, restore_users=False):
        """Restore a project from an encrypted backup."""
        try:
            # Extract ZIP contents
            zip_buffer = io.BytesIO(zip_data)
            with zipfile.ZipFile(zip_buffer, 'r') as zip_file:
                if 'backup.encrypted' not in zip_file.namelist():
                    raise ValueError("Invalid backup file: missing encrypted backup")
                
                if 'salt' not in zip_file.namelist():
                    raise ValueError("Invalid backup file: missing salt")
                
                encrypted_backup = zip_file.read('backup.encrypted').decode()
                salt = bytes.fromhex(zip_file.read('salt').decode())
            
            # Decrypt the backup
            key, _ = EncryptionManager.derive_key_from_password(password, salt)
            decrypted_data = EncryptionManager.decrypt_value(encrypted_backup, key)
            backup_data = json.loads(decrypted_data)
            
            # Restore the project
            return BackupManager.restore_project_backup(
                backup_data, 
                new_project_name, 
                restore_users
            )
            
        except Exception as e:
            raise ValueError(f"Failed to restore backup: {str(e)}")