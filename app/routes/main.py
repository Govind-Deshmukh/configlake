import io
import json
import logging
import os

from flask import Blueprint, current_app, jsonify, render_template, redirect, request, flash, send_file, url_for
from flask_login import login_required, current_user

from app import db
from app.models import Environment, Project, ProjectUser, User
from app.utils.backup import BackupManager
from app.utils.encryption import EncryptionManager

logger = logging.getLogger(__name__)

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        projects = Project.query.all()
    else:
        project_users = ProjectUser.query.filter_by(user_id=current_user.id).all()
        projects = [pu.project for pu in project_users]
    
    return render_template('dashboard.html', projects=projects)

@main_bp.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    users = User.query.all()
    
    # Get user statistics
    user_stats = []
    for user in users:
        project_count = ProjectUser.query.filter_by(user_id=user.id).count()
        owned_projects = ProjectUser.query.filter_by(user_id=user.id, role='owner').count()
        user_stats.append({
            'user': user,
            'project_count': project_count,
            'owned_projects': owned_projects
        })
    
    return render_template('admin/users.html', user_stats=user_stats)

@main_bp.route('/admin/users/<int:user_id>/toggle_admin', methods=['POST'])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    if user_id == current_user.id:
        flash('Cannot change your own admin status', 'error')
        return redirect(url_for('main.admin_users'))
    
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    
    status = 'granted' if user.is_admin else 'revoked'
    flash(f"Admin privileges {status} for user '{user.username}'", 'success')
    return redirect(url_for('main.admin_users'))

@main_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    if user_id == current_user.id:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('main.admin_users'))
    
    user = User.query.get_or_404(user_id)
    
    # Check if user is the sole owner of any projects
    sole_owner_projects = []
    owned_projects = ProjectUser.query.filter_by(user_id=user_id, role='owner').all()
    
    for project_user in owned_projects:
        owner_count = ProjectUser.query.filter_by(
            project_id=project_user.project_id,
            role='owner'
        ).count()
        if owner_count == 1:
            sole_owner_projects.append(project_user.project.name)
    
    if sole_owner_projects:
        flash(f"Cannot delete user. They are the sole owner of: {', '.join(sole_owner_projects)}", 'error')
        return redirect(url_for('main.admin_users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f"User '{username}' has been deleted", 'success')
    return redirect(url_for('main.admin_users'))


# ── Admin security panel ──────────────────────────────────────────────────

@main_bp.route('/admin/panel')
@login_required
def admin_panel():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))

    master_key = current_app.config.get('CONFIGLAKE_MASTER_KEY')
    total_envs    = Environment.query.count()
    wrapped_envs  = Environment.query.filter_by(key_is_wrapped=True).count()
    unwrapped_envs = total_envs - wrapped_envs

    return render_template(
        'admin/panel.html',
        master_key_loaded=bool(master_key),
        total_envs=total_envs,
        wrapped_envs=wrapped_envs,
        unwrapped_envs=unwrapped_envs,
    )


@main_bp.route('/admin/wrap-keys', methods=['POST'])
@login_required
def admin_wrap_keys():
    if not current_user.is_admin:
        return jsonify({'error': 'Admin privileges required'}), 403

    master_key = current_app.config.get('CONFIGLAKE_MASTER_KEY')
    if not master_key:
        return jsonify({'error': 'CONFIGLAKE_MASTER_KEY is not configured on this server'}), 400

    environments = Environment.query.filter_by(key_is_wrapped=False).all()
    if not environments:
        return jsonify({'message': 'All environment keys are already wrapped. Nothing to do.'})

    for env in environments:
        env.secret_key = EncryptionManager.wrap_env_key(env.secret_key, master_key)
        env.key_is_wrapped = True

    db.session.commit()
    logger.info("Admin wrapped %d environment key(s).", len(environments))
    return jsonify({'message': f'{len(environments)} environment key(s) wrapped successfully.'})


@main_bp.route('/admin/rotate-key', methods=['POST'])
@login_required
def admin_rotate_key():
    if not current_user.is_admin:
        return jsonify({'error': 'Admin privileges required'}), 403

    data = request.get_json()
    new_key = (data or {}).get('new_key', '').strip()

    if not new_key:
        return jsonify({'error': 'new_key is required'}), 422

    if not EncryptionManager.verify_key_format(new_key):
        return jsonify({'error': 'Invalid Fernet key format. Use the Generate button.'}), 422

    current_master_key = current_app.config.get('CONFIGLAKE_MASTER_KEY')
    if not current_master_key:
        return jsonify({'error': 'No master key is currently configured on this server'}), 400

    if new_key == current_master_key:
        return jsonify({'error': 'New key must be different from the current key'}), 422

    # Re-wrap every wrapped environment key with the new master key.
    wrapped_envs = Environment.query.filter_by(key_is_wrapped=True).all()
    for env in wrapped_envs:
        raw_key = EncryptionManager.unwrap_env_key(env.secret_key, current_master_key)
        env.secret_key = EncryptionManager.wrap_env_key(raw_key, new_key)

    db.session.commit()

    # Persist the new key to .env.
    _update_env_file('CONFIGLAKE_MASTER_KEY', new_key)

    logger.info("Master key rotated. %d environment key(s) re-wrapped.", len(wrapped_envs))
    return jsonify({
        'message': (
            f'Master key rotated. {len(wrapped_envs)} environment key(s) re-wrapped. '
            'Restart the server for the new key to take effect.'
        ),
        'restart_required': True,
    })


@main_bp.route('/admin/export')
@login_required
def admin_export():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))

    export_data = BackupManager.create_admin_export()
    json_bytes = json.dumps(export_data, indent=2).encode('utf-8')
    buf = io.BytesIO(json_bytes)
    buf.seek(0)

    from datetime import datetime
    filename = f"configlake_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.json"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype='application/json')


@main_bp.route('/admin/import', methods=['POST'])
@login_required
def admin_import():
    if not current_user.is_admin:
        return jsonify({'error': 'Admin privileges required'}), 403

    if 'file' not in request.files or request.files['file'].filename == '':
        return jsonify({'error': 'No file uploaded'}), 400

    overwrite = request.form.get('overwrite') == 'true'

    try:
        import_data = json.load(request.files['file'])
    except (json.JSONDecodeError, UnicodeDecodeError):
        return jsonify({'error': 'Invalid JSON file'}), 400

    try:
        results = BackupManager.restore_admin_import(import_data, overwrite=overwrite)
    except ValueError as exc:
        return jsonify({'error': str(exc)}), 422

    return jsonify({
        'message': 'Import complete.',
        'created':     results['created'],
        'overwritten': results['overwritten'],
        'skipped':     results['skipped'],
    })


@main_bp.route('/admin/restart', methods=['POST'])
@login_required
def admin_restart():
    if not current_user.is_admin:
        return jsonify({'error': 'Admin required'}), 403
    import threading
    def _do():
        import time
        time.sleep(1.0)
        os._exit(42)
    threading.Thread(target=_do, daemon=False).start()
    return jsonify({'ok': True})


@main_bp.route('/admin/cert-info')
@login_required
def admin_cert_info():
    if not current_user.is_admin:
        return jsonify({'error': 'Admin required'}), 403
    ssl_mode  = os.environ.get('SSL_MODE', '')
    cert_path = os.environ.get('SSL_CERT_PATH', '')
    return jsonify({
        'ssl_mode':  ssl_mode,
        'cert_path': cert_path,
        'cert':      _read_cert_info(cert_path) if cert_path else None,
    })


@main_bp.route('/admin/generate-key', methods=['POST'])
@login_required
def admin_generate_key():
    if not current_user.is_admin:
        return jsonify({'error': 'Admin required'}), 403
    return jsonify({'key': EncryptionManager.generate_key()})


@main_bp.route('/admin/renew-cert', methods=['POST'])
@login_required
def admin_renew_cert():
    if not current_user.is_admin:
        return jsonify({'error': 'Admin required'}), 403

    ssl_mode = os.environ.get('SSL_MODE', '')

    if ssl_mode == 'self-signed':
        from app.routes.setup import _generate_self_signed_cert
        _generate_self_signed_cert()
        return jsonify({
            'ok': True,
            'message': 'Self-signed certificate regenerated. Restart the server to apply it.',
            'restart_required': True,
        })

    if ssl_mode == 'manual':
        data         = request.get_json() or {}
        cert_content = (data.get('cert_content') or '').strip()
        key_content  = (data.get('key_content')  or '').strip()
        if not cert_content or not key_content:
            return jsonify({'error': 'Both certificate and private key are required.'}), 422
        if '-----BEGIN' not in cert_content or '-----BEGIN' not in key_content:
            return jsonify({'error': 'Content does not look like PEM format.'}), 422
        from app.routes.setup import _save_cert_content
        _save_cert_content(cert_content, key_content)
        return jsonify({
            'ok': True,
            'message': 'Certificate updated. Restart the server to apply it.',
            'restart_required': True,
        })

    return jsonify({'error': f'SSL mode is "{ssl_mode or "none"}" — certificate is managed externally.'}), 400


# ── Helpers ───────────────────────────────────────────────────────────────

def _read_cert_info(cert_path: str):
    """Return a dict of human-readable certificate fields, or {'error': ...}."""
    try:
        import datetime
        from cryptography import x509
        from cryptography.hazmat.backends import default_backend
        from cryptography.x509.oid import ExtensionOID, NameOID

        if not os.path.isfile(cert_path):
            return None

        with open(cert_path, 'rb') as f:
            cert = x509.load_pem_x509_certificate(f.read(), default_backend())

        now            = datetime.datetime.utcnow()
        days_remaining = (cert.not_valid_after - now).days

        cn_list     = cert.subject.get_attributes_for_oid(NameOID.COMMON_NAME)
        issuer_list = cert.issuer.get_attributes_for_oid(NameOID.COMMON_NAME)

        sans = []
        try:
            san_ext = cert.extensions.get_extension_for_oid(ExtensionOID.SUBJECT_ALTERNATIVE_NAME)
            sans = [str(n) for n in san_ext.value]
        except x509.ExtensionNotFound:
            pass

        return {
            'subject_cn':     cn_list[0].value     if cn_list     else 'Unknown',
            'issuer_cn':      issuer_list[0].value  if issuer_list else 'Unknown',
            'not_before':     cert.not_valid_before.strftime('%Y-%m-%d %H:%M UTC'),
            'not_after':      cert.not_valid_after.strftime('%Y-%m-%d %H:%M UTC'),
            'days_remaining': days_remaining,
            'is_self_signed': cert.subject == cert.issuer,
            'sans':           sans,
            'path':           cert_path,
        }
    except Exception as exc:
        return {'error': str(exc)}


def _update_env_file(key: str, value: str):
    """Write or update a single key in the root .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    new_line = f'{key}={value}\n'

    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f'{key}='):
                lines[i] = new_line
                updated = True
                break
        if not updated:
            lines.append(new_line)
        with open(env_path, 'w') as f:
            f.writelines(lines)
    else:
        with open(env_path, 'w') as f:
            f.write(new_line)