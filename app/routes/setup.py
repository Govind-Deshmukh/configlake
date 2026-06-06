import logging
import os

from flask import Blueprint, jsonify, redirect, render_template, request, url_for
from werkzeug.security import generate_password_hash

from app import db
from app.models import User
from app.utils.encryption import EncryptionManager

setup_bp = Blueprint('setup', __name__)
logger = logging.getLogger(__name__)


@setup_bp.route('/', methods=['GET'])
def index():
    if User.query.count() > 0:
        return redirect(url_for('auth.login'))
    return render_template('setup/index.html')


@setup_bp.route('/generate-key', methods=['POST'])
def generate_key():
    """Return a fresh Fernet key. Stateless — does not persist anything."""
    if User.query.count() > 0:
        return jsonify({'error': 'Setup already completed'}), 403
    key = EncryptionManager.generate_key()
    return jsonify({'key': key})


@setup_bp.route('/complete', methods=['POST'])
def complete():
    """Create the admin user and persist CONFIGLAKE_MASTER_KEY to .env."""
    if User.query.count() > 0:
        return jsonify({'error': 'Setup already completed'}), 403

    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    master_key = data.get('master_key', '').strip()
    username = data.get('username', '').strip()
    email = data.get('email', '').strip()
    password = data.get('password', '')
    confirm_password = data.get('confirm_password', '')

    # Validate all fields
    errors = {}
    if not master_key:
        errors['master_key'] = 'Master key is required.'
    elif not EncryptionManager.verify_key_format(master_key):
        errors['master_key'] = 'Invalid Fernet key format. Use the Generate button to create one.'

    if not username:
        errors['username'] = 'Username is required.'
    elif len(username) < 3:
        errors['username'] = 'Username must be at least 3 characters.'

    if not email or '@' not in email:
        errors['email'] = 'A valid email address is required.'

    if not password:
        errors['password'] = 'Password is required.'
    elif len(password) < 8:
        errors['password'] = 'Password must be at least 8 characters.'
    elif password != confirm_password:
        errors['confirm_password'] = 'Passwords do not match.'

    if errors:
        return jsonify({'errors': errors}), 422

    # Persist master key to .env so the app can use it on next start
    _write_master_key_to_env(master_key)

    # Create admin user
    admin = User(username=username, email=email, is_admin=True)
    admin.set_password(password)
    db.session.add(admin)
    db.session.commit()

    logger.info("Setup completed. Admin user '%s' created.", username)
    return jsonify({'redirect': url_for('setup.done')})


@setup_bp.route('/done', methods=['GET'])
def done():
    return render_template('setup/done.html', over_http=request.scheme == 'http')


def _write_master_key_to_env(master_key: str):
    """Write or update CONFIGLAKE_MASTER_KEY in the .env file."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env')
    new_line = f'CONFIGLAKE_MASTER_KEY={master_key}\n'

    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            lines = f.readlines()

        updated = False
        for i, line in enumerate(lines):
            if line.startswith('CONFIGLAKE_MASTER_KEY='):
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
