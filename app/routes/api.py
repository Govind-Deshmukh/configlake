from flask import Blueprint, request, jsonify, g
from flask_login import login_required
from app import db
from app.models import Project, Environment, Config, Secret, APIToken
from app.utils.encryption import EncryptionManager
from app.utils.security import require_api_token, require_project_permission
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