from flask import Blueprint, request, jsonify, g
from flask_login import login_required
from app import db
from app.models import Project, Environment, Config, Secret, APIToken
from app.utils.encryption import EncryptionManager
from app.utils.security import require_api_token, require_project_permission, require_project_permission_with_ip
from datetime import datetime, timedelta
import secrets

api_bp = Blueprint('api', __name__)

# READ-ONLY API endpoints for applications
@api_bp.route('/config/<int:project_id>/<environment_name>')
@require_api_token()
def get_config(project_id, environment_name):
    """Get all configs for a specific project and environment."""
    if g.api_token.project_id != project_id:
        return jsonify({'error': 'Token not valid for this project'}), 403
    
    environment = Environment.query.filter_by(
        project_id=project_id,
        name=environment_name
    ).first()
    
    if not environment or g.api_token.environment_id != environment.id:
        return jsonify({'error': 'Environment not found or not accessible'}), 404
    
    configs = Config.query.filter_by(environment_id=environment.id).all()
    
    config_data = {}
    for config in configs:
        config_data[config.key] = config.value
    
    return jsonify({
        'project_id': project_id,
        'environment': environment_name,
        'configs': config_data
    })

@api_bp.route('/secrets/<int:project_id>/<environment_name>')
@require_api_token()
def get_secrets(project_id, environment_name):
    """Get all encrypted secrets for a specific project and environment."""
    if g.api_token.project_id != project_id:
        return jsonify({'error': 'Token not valid for this project'}), 403
    
    environment = Environment.query.filter_by(
        project_id=project_id,
        name=environment_name
    ).first()
    
    if not environment or g.api_token.environment_id != environment.id:
        return jsonify({'error': 'Environment not found or not accessible'}), 404
    
    secrets_query = Secret.query.filter_by(environment_id=environment.id).all()
    
    secret_data = {}
    for secret in secrets_query:
        secret_data[secret.key] = secret.encrypted_value
    
    return jsonify({
        'project_id': project_id,
        'environment': environment_name,
        'environment_key': environment.secret_key,
        'secrets': secret_data
    })

@api_bp.route('/all/<int:project_id>/<environment_name>')
@require_api_token()
def get_all(project_id, environment_name):
    """Get both configs and secrets for a specific project and environment."""
    if g.api_token.project_id != project_id:
        return jsonify({'error': 'Token not valid for this project'}), 403
    
    environment = Environment.query.filter_by(
        project_id=project_id,
        name=environment_name
    ).first()
    
    if not environment or g.api_token.environment_id != environment.id:
        return jsonify({'error': 'Environment not found or not accessible'}), 404
    
    configs = Config.query.filter_by(environment_id=environment.id).all()
    secrets_query = Secret.query.filter_by(environment_id=environment.id).all()
    
    config_data = {}
    for config in configs:
        config_data[config.key] = config.value
    
    secret_data = {}
    for secret in secrets_query:
        secret_data[secret.key] = secret.encrypted_value
    
    return jsonify({
        'project_id': project_id,
        'environment': environment_name,
        'environment_key': environment.secret_key,
        'configs': config_data,
        'secrets': secret_data
    })

# Token management endpoints - Only accessible via web UI with login
@api_bp.route('/manage/token/<int:project_id>/<int:environment_id>', methods=['POST'])
@login_required
@require_project_permission('owner')
def create_api_token(project_id, environment_id):
    """Create a new API token for accessing configs/secrets."""
    data = request.get_json()
    token_name = data.get('name') if data else 'API Token'
    
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    token = EncryptionManager.generate_api_token()
    expires_at = datetime.utcnow() + timedelta(days=365)  # 1 year expiry
    
    api_token = APIToken(
        token=token,
        project_id=project_id,
        environment_id=environment_id,
        name=token_name,
        expires_at=expires_at
    )
    
    db.session.add(api_token)
    db.session.commit()
    
    return jsonify({
        'token': token,
        'name': token_name,
        'expires_at': expires_at.isoformat(),
        'message': 'API token created successfully'
    })

@api_bp.route('/manage/token/<int:project_id>/<int:environment_id>/<int:token_id>', methods=['DELETE'])
@login_required
@require_project_permission('owner')
def revoke_api_token(project_id, environment_id, token_id):
    """Revoke (delete) an API token."""
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    api_token = APIToken.query.filter_by(
        id=token_id,
        project_id=project_id,
        environment_id=environment_id
    ).first()
    
    if not api_token:
        return jsonify({'error': 'API token not found'}), 404
    
    db.session.delete(api_token)
    db.session.commit()
    
    return jsonify({'message': 'API token revoked successfully'})

@api_bp.route('/manage/token/<int:project_id>/<int:environment_id>/<int:token_id>/toggle', methods=['POST'])
@login_required
@require_project_permission('owner')
def toggle_api_token(project_id, environment_id, token_id):
    """Toggle API token active status."""
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    api_token = APIToken.query.filter_by(
        id=token_id,
        project_id=project_id,
        environment_id=environment_id
    ).first()
    
    if not api_token:
        return jsonify({'error': 'API token not found'}), 404
    
    api_token.is_active = not api_token.is_active
    db.session.commit()
    
    status = 'activated' if api_token.is_active else 'deactivated'
    return jsonify({'message': f'API token {status} successfully', 'is_active': api_token.is_active})

# Configuration and Secrets Management endpoints
@api_bp.route('/manage/config/<int:project_id>/<environment_name>', methods=['POST'])
@login_required
@require_project_permission('write')
def manage_config(project_id, environment_name):
    """Save/update configurations and secrets for an environment."""
    data = request.get_json()
    
    print(f"DEBUG: manage_config called with project_id={project_id}, environment_name='{environment_name}'")
    print(f"DEBUG: Received data: {data}")
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    environment = Environment.query.filter_by(
        project_id=project_id,
        name=environment_name
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    # Handle both individual key-value pairs and bulk configs/secrets
    if 'key' in data and 'value' in data:
        # Individual config format: { "key": "name", "value": "val" }
        configs = {data['key']: data['value']}
        secrets = {}
    else:
        # Bulk format: { "configs": {...}, "secrets": {...} }
        configs = data.get('configs', {})
        secrets = data.get('secrets', {})
    
    try:
        # Handle configs
        for key, value in configs.items():
            existing_config = Config.query.filter_by(
                environment_id=environment.id,
                key=key
            ).first()
            
            if existing_config:
                existing_config.value = value
            else:
                new_config = Config(
                    environment_id=environment.id,
                    key=key,
                    value=value
                )
                db.session.add(new_config)
        
        # Handle secrets
        encryption_manager = EncryptionManager()
        for key, value in secrets.items():
            existing_secret = Secret.query.filter_by(
                environment_id=environment.id,
                key=key
            ).first()
            
            encrypted_value = encryption_manager.encrypt_value(value, environment.secret_key)
            
            if existing_secret:
                existing_secret.encrypted_value = encrypted_value
            else:
                new_secret = Secret(
                    environment_id=environment.id,
                    key=key,
                    encrypted_value=encrypted_value
                )
                db.session.add(new_secret)
        
        db.session.commit()
        
        # Verify data was saved
        saved_configs = Config.query.filter_by(environment_id=environment.id).count()
        saved_secrets = Secret.query.filter_by(environment_id=environment.id).count()
        
        return jsonify({
            'message': 'Configuration saved successfully',
            'configs_updated': len(configs),
            'secrets_updated': len(secrets),
            'total_configs': saved_configs,
            'total_secrets': saved_secrets
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to save configuration: {str(e)}'}), 500

@api_bp.route('/manage/config/<int:project_id>/<environment_name>/<key>', methods=['DELETE'])
@login_required
@require_project_permission('write')
def delete_config_key(project_id, environment_name, key):
    """Delete a specific configuration or secret key."""
    environment = Environment.query.filter_by(
        project_id=project_id,
        name=environment_name
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    # Try to find and delete config
    config = Config.query.filter_by(
        environment_id=environment.id,
        key=key
    ).first()
    
    if config:
        db.session.delete(config)
        db.session.commit()
        return jsonify({'message': f'Config key "{key}" deleted successfully'})
    
    # Try to find and delete secret
    secret = Secret.query.filter_by(
        environment_id=environment.id,
        key=key
    ).first()
    
    if secret:
        db.session.delete(secret)
        db.session.commit()
        return jsonify({'message': f'Secret key "{key}" deleted successfully'})
    
    return jsonify({'error': f'Key "{key}" not found'}), 404

# Debug endpoint to verify configs and secrets are saved
@api_bp.route('/debug/config/<int:project_id>/<environment_name>')
@login_required
def debug_config(project_id, environment_name):
    """Debug endpoint to check saved configs and secrets."""
    environment = Environment.query.filter_by(
        project_id=project_id,
        name=environment_name
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    configs = Config.query.filter_by(environment_id=environment.id).all()
    secrets = Secret.query.filter_by(environment_id=environment.id).all()
    
    config_data = [{'key': c.key, 'value': c.value, 'id': c.id} for c in configs]
    secret_data = [{'key': s.key, 'id': s.id} for s in secrets]
    
    return jsonify({
        'environment_id': environment.id,
        'environment_name': environment.name,
        'configs_count': len(configs),
        'secrets_count': len(secrets),
        'configs': config_data,
        'secrets': secret_data
    })

# Separate endpoints for configs and secrets (for backward compatibility with templates)
@api_bp.route('/manage/secret/<int:project_id>/<environment_name>', methods=['POST'])
@login_required
@require_project_permission('write')
def manage_secret(project_id, environment_name):
    """Save/update secrets for an environment."""
    data = request.get_json()
    
    print(f"DEBUG: manage_secret called with project_id={project_id}, environment_name='{environment_name}'")
    print(f"DEBUG: Received data: {data}")
    
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    
    environment = Environment.query.filter_by(
        project_id=project_id,
        name=environment_name
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    # Handle individual key-value pairs for secrets
    if 'key' in data and 'value' in data:
        # Individual secret format: { "key": "name", "value": "val" }
        secrets = {data['key']: data['value']}
    else:
        # Bulk format: { "secrets": {...} }
        secrets = data.get('secrets', {})
    
    try:
        # Handle secrets
        encryption_manager = EncryptionManager()
        for key, value in secrets.items():
            existing_secret = Secret.query.filter_by(
                environment_id=environment.id,
                key=key
            ).first()
            
            encrypted_value = encryption_manager.encrypt_value(value, environment.secret_key)
            
            if existing_secret:
                existing_secret.encrypted_value = encrypted_value
            else:
                new_secret = Secret(
                    environment_id=environment.id,
                    key=key,
                    encrypted_value=encrypted_value
                )
                db.session.add(new_secret)
        
        db.session.commit()
        
        # Verify data was saved
        saved_secrets = Secret.query.filter_by(environment_id=environment.id).count()
        
        return jsonify({
            'message': 'Secrets saved successfully',
            'secrets_updated': len(secrets),
            'total_secrets': saved_secrets
        })
    
    except Exception as e:
        db.session.rollback()
        return jsonify({'error': f'Failed to save secrets: {str(e)}'}), 500

# Utility endpoint for testing - clear all configs/secrets for an environment
@api_bp.route('/debug/clear/<int:project_id>/<environment_name>', methods=['POST'])
@login_required
@require_project_permission('write')
def clear_environment_data(project_id, environment_name):
    """Clear all configs and secrets for testing purposes."""
    environment = Environment.query.filter_by(
        project_id=project_id,
        name=environment_name
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    # Clear all configs and secrets
    Config.query.filter_by(environment_id=environment.id).delete()
    Secret.query.filter_by(environment_id=environment.id).delete()
    db.session.commit()
    
    return jsonify({'message': 'Environment data cleared successfully'})

# Test endpoint to verify IP whitelisting behavior
@api_bp.route('/test/ip-check/<int:project_id>')
@login_required
@require_project_permission_with_ip('reader')
def test_ip_check(project_id):
    """Test endpoint that enforces IP whitelisting."""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR') or request.remote_addr
    return jsonify({
        'message': 'IP check passed!',
        'project_id': project_id,
        'client_ip': client_ip,
        'note': 'This endpoint enforces IP whitelisting'
    })

@api_bp.route('/test/no-ip-check/<int:project_id>')
@login_required
@require_project_permission('reader')
def test_no_ip_check(project_id):
    """Test endpoint that bypasses IP whitelisting."""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR') or request.remote_addr
    return jsonify({
        'message': 'No IP check - dashboard access!',
        'project_id': project_id,
        'client_ip': client_ip,
        'note': 'This endpoint bypasses IP whitelisting (for dashboard)'
    })