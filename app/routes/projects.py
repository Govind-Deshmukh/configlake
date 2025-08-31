from flask import Blueprint, render_template, request, redirect, url_for, flash, jsonify, send_file
from flask_login import login_required, current_user
from app import db
from app.models import Project, Environment, ProjectUser, User, Config, Secret, AllowedIP, APIToken
from app.utils.encryption import EncryptionManager
from app.utils.security import require_project_permission
from app.utils.backup import BackupManager
from datetime import datetime
import io

projects_bp = Blueprint('projects', __name__)

@projects_bp.route('/')
@login_required
def list_projects():
    if current_user.is_admin:
        projects = Project.query.all()
    else:
        project_users = ProjectUser.query.filter_by(user_id=current_user.id).all()
        projects = [pu.project for pu in project_users]
    
    return render_template('projects/list.html', projects=projects)

@projects_bp.route('/create', methods=['GET', 'POST'])
@login_required
def create_project():
    if request.method == 'POST':
        name = request.form.get('name')
        description = request.form.get('description', '')
        
        if not name:
            flash('Project name is required', 'error')
            return render_template('projects/create.html')
        
        # Check if project name already exists
        existing_project = Project.query.filter_by(name=name).first()
        if existing_project:
            flash('Project name already exists', 'error')
            return render_template('projects/create.html')
        
        project = Project(name=name, description=description)
        db.session.add(project)
        db.session.flush()  # Get the project ID
        
        # Add current user as owner
        project_user = ProjectUser(
            user_id=current_user.id,
            project_id=project.id,
            role='owner'
        )
        db.session.add(project_user)
        db.session.commit()
        
        flash('Project created successfully', 'success')
        return redirect(url_for('projects.view_project', project_id=project.id))
    
    return render_template('projects/create.html')

@projects_bp.route('/<int:project_id>')
@login_required
@require_project_permission('reader')
def view_project(project_id):
    project = Project.query.get_or_404(project_id)
    environments = Environment.query.filter_by(project_id=project_id).all()
    
    return render_template('projects/view.html', project=project, environments=environments)

@projects_bp.route('/<int:project_id>/environment/create', methods=['GET', 'POST'])
@login_required
@require_project_permission('owner')
def create_environment(project_id):
    project = Project.query.get_or_404(project_id)
    
    if request.method == 'POST':
        name = request.form.get('name')
        
        if not name:
            flash('Environment name is required', 'error')
            return render_template('projects/create_environment.html', project=project)
        
        # Check if environment already exists in this project
        existing_env = Environment.query.filter_by(
            name=name,
            project_id=project_id
        ).first()
        
        if existing_env:
            flash('Environment already exists in this project', 'error')
            return render_template('projects/create_environment.html', project=project)
        
        # Generate encryption key for this environment
        secret_key = EncryptionManager.generate_key()
        
        environment = Environment(
            name=name,
            project_id=project_id,
            secret_key=secret_key
        )
        db.session.add(environment)
        db.session.commit()
        
        flash('Environment created successfully', 'success')
        return redirect(url_for('projects.view_project', project_id=project_id))
    
    return render_template('projects/create_environment.html', project=project)

@projects_bp.route('/<int:project_id>/environment/<int:environment_id>')
@login_required
@require_project_permission('reader')
def view_environment(project_id, environment_id):
    project = Project.query.get_or_404(project_id)
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first_or_404()
    
    configs = Config.query.filter_by(environment_id=environment_id).all()
    secrets = Secret.query.filter_by(environment_id=environment_id).all()
    api_tokens = APIToken.query.filter_by(
        project_id=project_id,
        environment_id=environment_id,
        is_active=True
    ).all()
    
    # Debug output
    print(f"DEBUG: Environment ID: {environment_id}")
    print(f"DEBUG: Configs found: {len(configs)}")
    print(f"DEBUG: Secrets found: {len(secrets)}")
    if configs:
        for config in configs:
            print(f"DEBUG: Config - {config.key}: {config.value}")
    if secrets:
        for secret in secrets:
            print(f"DEBUG: Secret - {secret.key}")
    print(f"DEBUG: API tokens: {len(api_tokens)}")
    
    # Get environment-specific allowed IPs (backward compatible)
    environment_ips = []
    try:
        if hasattr(AllowedIP, 'environment_id'):
            environment_ips = AllowedIP.query.filter_by(
                project_id=project_id,
                environment_id=environment_id
            ).all()
    except Exception:
        # Column doesn't exist yet, skip environment-specific IPs
        pass
    
    return render_template('projects/environment.html', 
                         project=project, 
                         environment=environment, 
                         configs=configs, 
                         secrets=secrets,
                         api_tokens=api_tokens,
                         environment_ips=environment_ips)

@projects_bp.route('/<int:project_id>/users')
@login_required
@require_project_permission('owner')
def manage_users(project_id):
    project = Project.query.get_or_404(project_id)
    project_users = ProjectUser.query.filter_by(project_id=project_id).all()
    all_users = User.query.all()
    
    return render_template('projects/users.html', 
                         project=project, 
                         project_users=project_users,
                         all_users=all_users)

@projects_bp.route('/<int:project_id>/users/add', methods=['POST'])
@login_required
@require_project_permission('owner')
def add_user(project_id):
    user_id = request.form.get('user_id')
    role = request.form.get('role', 'reader')
    
    if not user_id:
        flash('User is required', 'error')
        return redirect(url_for('projects.manage_users', project_id=project_id))
    
    # Check if user is already in the project
    existing = ProjectUser.query.filter_by(
        user_id=user_id,
        project_id=project_id
    ).first()
    
    if existing:
        flash('User is already in this project', 'error')
        return redirect(url_for('projects.manage_users', project_id=project_id))
    
    project_user = ProjectUser(
        user_id=user_id,
        project_id=project_id,
        role=role
    )
    db.session.add(project_user)
    db.session.commit()
    
    flash('User added to project successfully', 'success')
    return redirect(url_for('projects.manage_users', project_id=project_id))

@projects_bp.route('/<int:project_id>/users/<int:user_id>/remove', methods=['POST'])
@login_required
@require_project_permission('owner')
def remove_user(project_id, user_id):
    project_user = ProjectUser.query.filter_by(
        user_id=user_id,
        project_id=project_id
    ).first_or_404()
    
    # Prevent removing yourself if you're the only owner
    if user_id == current_user.id:
        owners = ProjectUser.query.filter_by(
            project_id=project_id,
            role='owner'
        ).count()
        
        if owners <= 1:
            flash('Cannot remove the last owner from the project', 'error')
            return redirect(url_for('projects.manage_users', project_id=project_id))
    
    db.session.delete(project_user)
    db.session.commit()
    
    flash('User removed from project', 'success')
    return redirect(url_for('projects.manage_users', project_id=project_id))

@projects_bp.route('/<int:project_id>/users/<int:user_id>/role', methods=['POST'])
@login_required
@require_project_permission('owner')
def change_user_role(project_id, user_id):
    project_user = ProjectUser.query.filter_by(
        user_id=user_id,
        project_id=project_id
    ).first_or_404()
    
    new_role = request.form.get('role')
    if new_role not in ['owner', 'maintainer', 'reader']:
        flash('Invalid role specified', 'error')
        return redirect(url_for('projects.manage_users', project_id=project_id))
    
    # Prevent changing your own role if you're the only owner
    if user_id == current_user.id and project_user.role == 'owner':
        owners = ProjectUser.query.filter_by(
            project_id=project_id,
            role='owner'
        ).count()
        
        if owners <= 1 and new_role != 'owner':
            flash('Cannot change role: You are the only owner of this project', 'error')
            return redirect(url_for('projects.manage_users', project_id=project_id))
    
    old_role = project_user.role
    project_user.role = new_role
    db.session.commit()
    
    user = User.query.get(user_id)
    flash(f"User '{user.username}' role changed from {old_role} to {new_role}", 'success')
    return redirect(url_for('projects.manage_users', project_id=project_id))


@projects_bp.route('/<int:project_id>/security')
@login_required
@require_project_permission('owner')
def manage_security(project_id):
    project = Project.query.get_or_404(project_id)
    allowed_ips = AllowedIP.query.filter_by(project_id=project_id).all()
    
    return render_template('projects/security.html', 
                         project=project, 
                         allowed_ips=allowed_ips)

@projects_bp.route('/<int:project_id>/security/ip', methods=['POST'])
@login_required
@require_project_permission('owner')
def add_allowed_ip(project_id):
    ip_address = request.form.get('ip_address')
    description = request.form.get('description', '')
    
    if not ip_address:
        flash('IP address is required', 'error')
        return redirect(url_for('projects.manage_security', project_id=project_id))
    
    # Validate IP address or FQDN format (now supports IP:port format)
    import ipaddress as ip_module
    import socket
    import re
    
    is_fqdn = False
    
    # Check if IP has port (e.g., 127.0.0.1:3000 or localhost:3000)
    port_pattern = r'^(.+):(\d+)$'
    port_match = re.match(port_pattern, ip_address)
    
    if port_match:
        # Extract IP/hostname and port
        host_part = port_match.group(1)
        port_part = port_match.group(2)
        
        # Validate port number
        try:
            port_num = int(port_part)
            if not (1 <= port_num <= 65535):
                flash('Port number must be between 1 and 65535', 'error')
                return redirect(url_for('projects.manage_security', project_id=project_id))
        except ValueError:
            flash('Invalid port number', 'error')
            return redirect(url_for('projects.manage_security', project_id=project_id))
        
        # Validate the host part
        try:
            if '/' in host_part:
                ip_module.ip_network(host_part, strict=False)
            else:
                ip_module.ip_address(host_part)
        except ValueError:
            # Check if it's a valid hostname
            try:
                socket.getaddrinfo(host_part, None)
                is_fqdn = True
            except socket.gaierror:
                flash('Invalid IP address or hostname in IP:port format', 'error')
                return redirect(url_for('projects.manage_security', project_id=project_id))
    else:
        # Original validation logic for IP/CIDR/FQDN without port
        try:
            # Try to validate as IP address or CIDR first
            if '/' in ip_address:
                ip_module.ip_network(ip_address, strict=False)
            else:
                ip_module.ip_address(ip_address)
        except ValueError:
            # If not a valid IP, check if it's a valid FQDN
            try:
                socket.getaddrinfo(ip_address, None)
                is_fqdn = True
            except socket.gaierror:
                flash('Invalid IP address, CIDR, hostname, or IP:port format', 'error')
                return redirect(url_for('projects.manage_security', project_id=project_id))
    
    allowed_ip = AllowedIP(
        ip_address=ip_address,
        project_id=project_id,
        description=description,
        is_fqdn=is_fqdn
    )
    db.session.add(allowed_ip)
    db.session.commit()
    
    flash('IP address added successfully', 'success')
    return redirect(url_for('projects.manage_security', project_id=project_id))

@projects_bp.route('/<int:project_id>/security/ip/<int:ip_id>/remove', methods=['POST'])
@login_required
@require_project_permission('owner')
def remove_allowed_ip(project_id, ip_id):
    allowed_ip = AllowedIP.query.filter_by(
        id=ip_id,
        project_id=project_id
    ).first_or_404()
    
    db.session.delete(allowed_ip)
    db.session.commit()
    
    flash('IP address removed', 'success')
    return redirect(url_for('projects.manage_security', project_id=project_id))

@projects_bp.route('/<int:project_id>/backup')
@login_required
@require_project_permission('owner')
def backup_project(project_id):
    """Display backup options for a project."""
    project = Project.query.get_or_404(project_id)
    return render_template('projects/backup.html', project=project)

@projects_bp.route('/<int:project_id>/backup/download', methods=['POST'])
@login_required
@require_project_permission('owner')
def download_backup(project_id):
    """Download an encrypted backup of the project."""
    project = Project.query.get_or_404(project_id)
    
    password = request.form.get('password')
    include_users = request.form.get('include_users') == 'on'
    
    if not password:
        flash('Password is required for backup encryption', 'error')
        return redirect(url_for('projects.backup_project', project_id=project_id))
    
    try:
        backup_data = BackupManager.create_encrypted_backup(
            project_id, 
            password, 
            include_users
        )
        
        # Create a file-like object for download
        backup_file = io.BytesIO(backup_data)
        backup_file.seek(0)
        
        filename = f"{project.name}_backup_{datetime.now().strftime('%Y%m%d_%H%M%S')}.zip"
        
        return send_file(
            backup_file,
            as_attachment=True,
            download_name=filename,
            mimetype='application/zip'
        )
        
    except Exception as e:
        flash(f'Backup failed: {str(e)}', 'error')
        return redirect(url_for('projects.backup_project', project_id=project_id))

@projects_bp.route('/restore', methods=['GET', 'POST'])
@login_required
def restore_project():
    """Restore a project from backup."""
    if request.method == 'POST':
        if 'backup_file' not in request.files:
            flash('No backup file selected', 'error')
            return render_template('projects/restore.html')
        
        file = request.files['backup_file']
        if file.filename == '':
            flash('No backup file selected', 'error')
            return render_template('projects/restore.html')
        
        password = request.form.get('password')
        new_project_name = request.form.get('new_project_name')
        restore_users = request.form.get('restore_users') == 'on'
        
        if not password:
            flash('Password is required to decrypt backup', 'error')
            return render_template('projects/restore.html')
        
        try:
            backup_data = file.read()
            project = BackupManager.restore_encrypted_backup(
                backup_data,
                password,
                new_project_name,
                restore_users
            )
            
            # Add current user as owner of restored project
            project_user = ProjectUser(
                user_id=current_user.id,
                project_id=project.id,
                role='owner'
            )
            db.session.add(project_user)
            db.session.commit()
            
            flash(f'Project "{project.name}" restored successfully!', 'success')
            return redirect(url_for('projects.view_project', project_id=project.id))
            
        except Exception as e:
            flash(f'Restore failed: {str(e)}', 'error')
            return render_template('projects/restore.html')
    
    return render_template('projects/restore.html')

@projects_bp.route('/<int:project_id>/environment/<int:environment_id>/ip', methods=['POST'])
@login_required
@require_project_permission('owner')
def add_environment_ip(project_id, environment_id):
    """Add an IP to environment-specific whitelist."""
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first_or_404()
    
    ip_address = request.form.get('ip_address')
    description = request.form.get('description', '')
    
    if not ip_address:
        return jsonify({'error': 'IP address is required'}), 400
    
    # Validate IP address or FQDN format (now supports IP:port format)
    import ipaddress as ip_module
    import socket
    import re
    
    is_fqdn = False
    
    # Check if IP has port (e.g., 127.0.0.1:3000 or localhost:3000)
    port_pattern = r'^(.+):(\d+)$'
    port_match = re.match(port_pattern, ip_address)
    
    if port_match:
        # Extract IP/hostname and port
        host_part = port_match.group(1)
        port_part = port_match.group(2)
        
        # Validate port number
        try:
            port_num = int(port_part)
            if not (1 <= port_num <= 65535):
                return jsonify({'error': 'Port number must be between 1 and 65535'}), 400
        except ValueError:
            return jsonify({'error': 'Invalid port number'}), 400
        
        # Validate the host part
        try:
            if '/' in host_part:
                ip_module.ip_network(host_part, strict=False)
            else:
                ip_module.ip_address(host_part)
        except ValueError:
            # Check if it's a valid hostname
            try:
                socket.getaddrinfo(host_part, None)
                is_fqdn = True
            except socket.gaierror:
                return jsonify({'error': 'Invalid IP address or hostname in IP:port format'}), 400
    else:
        # Original validation logic for IP/CIDR/FQDN without port
        try:
            # Try to validate as IP address or CIDR first
            if '/' in ip_address:
                ip_module.ip_network(ip_address, strict=False)
            else:
                ip_module.ip_address(ip_address)
        except ValueError:
            # If not a valid IP, check if it's a valid FQDN
            try:
                socket.getaddrinfo(ip_address, None)
                is_fqdn = True
            except socket.gaierror:
                return jsonify({'error': 'Invalid IP address, CIDR, hostname, or IP:port format'}), 400
    
    allowed_ip = AllowedIP(
        ip_address=ip_address,
        project_id=project_id,
        environment_id=environment_id,
        description=description,
        is_fqdn=is_fqdn
    )
    db.session.add(allowed_ip)
    db.session.commit()
    
    return jsonify({'message': 'IP added successfully'})

@projects_bp.route('/<int:project_id>/environment/<int:environment_id>/ips', methods=['GET'])
@login_required
@require_project_permission('reader')
def get_environment_ips(project_id, environment_id):
    """Get environment-specific IP whitelist."""
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first_or_404()
    
    allowed_ips = AllowedIP.query.filter_by(
        project_id=project_id,
        environment_id=environment_id
    ).all()
    
    ips = []
    for ip in allowed_ips:
        ips.append({
            'id': ip.id,
            'ip_address': ip.ip_address,
            'description': ip.description,
            'created_at': ip.created_at.strftime('%Y-%m-%d %H:%M')
        })
    
    return jsonify({'ips': ips})

@projects_bp.route('/<int:project_id>/environment/<int:environment_id>/ip/<int:ip_id>', methods=['DELETE'])
@login_required
@require_project_permission('owner')
def remove_environment_ip(project_id, environment_id, ip_id):
    """Remove an IP from environment-specific whitelist."""
    allowed_ip = AllowedIP.query.filter_by(
        id=ip_id,
        project_id=project_id,
        environment_id=environment_id
    ).first_or_404()
    
    db.session.delete(allowed_ip)
    db.session.commit()
    
    return jsonify({'message': 'IP removed successfully'})

# Config and Secret management routes
@projects_bp.route('/<int:project_id>/environment/<int:environment_id>/config', methods=['POST'])
@login_required
@require_project_permission('maintainer')
def create_config(project_id, environment_id):
    """Create or update a configuration value."""
    data = request.get_json()
    
    if not data or 'key' not in data or 'value' not in data:
        return jsonify({'error': 'Key and value are required'}), 400
    
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    # Check if config already exists
    config = Config.query.filter_by(
        key=data['key'],
        environment_id=environment.id
    ).first()
    
    if config:
        config.value = data['value']
        config.updated_at = datetime.utcnow()
    else:
        config = Config(
            key=data['key'],
            value=data['value'],
            environment_id=environment.id
        )
        db.session.add(config)
    
    db.session.commit()
    
    return jsonify({
        'message': 'Configuration saved successfully',
        'key': config.key
    })

@projects_bp.route('/<int:project_id>/environment/<int:environment_id>/secret', methods=['POST'])
@login_required
@require_project_permission('maintainer')
def create_secret(project_id, environment_id):
    """Create or update a secret value."""
    data = request.get_json()
    
    if not data or 'key' not in data or 'value' not in data:
        return jsonify({'error': 'Key and value are required'}), 400
    
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    try:
        # Encrypt the secret value
        encrypted_value = EncryptionManager.encrypt_value(
            data['value'],
            environment.secret_key
        )
        
        # Check if secret already exists
        secret = Secret.query.filter_by(
            key=data['key'],
            environment_id=environment.id
        ).first()
        
        if secret:
            secret.encrypted_value = encrypted_value
            secret.updated_at = datetime.utcnow()
        else:
            secret = Secret(
                key=data['key'],
                encrypted_value=encrypted_value,
                environment_id=environment.id
            )
            db.session.add(secret)
        
        db.session.commit()
        
        return jsonify({
            'message': 'Secret saved successfully',
            'key': secret.key
        })
    
    except Exception as e:
        return jsonify({'error': f'Failed to encrypt secret: {str(e)}'}), 500

@projects_bp.route('/<int:project_id>/environment/<int:environment_id>/config/<config_key>/delete', methods=['POST'])
@login_required
@require_project_permission('maintainer')
def delete_config(project_id, environment_id, config_key):
    """Delete a configuration value."""
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    config = Config.query.filter_by(
        key=config_key,
        environment_id=environment.id
    ).first()
    
    if not config:
        return jsonify({'error': 'Configuration not found'}), 404
    
    db.session.delete(config)
    db.session.commit()
    
    flash('Configuration deleted successfully', 'success')
    return redirect(url_for('projects.view_environment', project_id=project_id, environment_id=environment_id))

@projects_bp.route('/<int:project_id>/environment/<int:environment_id>/secret/<secret_key>/delete', methods=['POST'])
@login_required
@require_project_permission('maintainer')
def delete_secret(project_id, environment_id, secret_key):
    """Delete a secret value."""
    environment = Environment.query.filter_by(
        id=environment_id,
        project_id=project_id
    ).first()
    
    if not environment:
        return jsonify({'error': 'Environment not found'}), 404
    
    secret = Secret.query.filter_by(
        key=secret_key,
        environment_id=environment.id
    ).first()
    
    if not secret:
        return jsonify({'error': 'Secret not found'}), 404
    
    db.session.delete(secret)
    db.session.commit()
    
    flash('Secret deleted successfully', 'success')
    return redirect(url_for('projects.view_environment', project_id=project_id, environment_id=environment_id))