import datetime
import ipaddress
import logging
import os

from flask import Blueprint, jsonify, redirect, render_template, request, session, url_for

from app.utils.encryption import EncryptionManager

setup_bp = Blueprint('setup', __name__)
logger = logging.getLogger(__name__)


def _setup_only():
    """Return a 403 JSON response if setup has already been completed (users exist)."""
    from app.models import User
    if User.query.count() > 0:
        return jsonify({'error': 'Setup already completed'}), 403
    return None


@setup_bp.route('/', methods=['GET'])
def index():
    from app.models import User
    if User.query.count() > 0:
        return redirect(url_for('auth.login'))
    return render_template('setup/index.html')


@setup_bp.route('/generate-key', methods=['POST'])
def generate_key():
    err = _setup_only()
    if err:
        return err
    return jsonify({'key': EncryptionManager.generate_key()})


@setup_bp.route('/test-db', methods=['POST'])
def test_db():
    err = _setup_only()
    if err:
        return err
    data = request.get_json() or {}
    db_type = data.get('db_type', 'sqlite')

    if db_type == 'sqlite':
        return jsonify({'ok': True, 'message': 'SQLite is built-in — no connection needed.'})

    uri = _build_db_uri(data)
    try:
        from sqlalchemy import create_engine, text
        kwargs = {'connect_args': {'connect_timeout': 5}} if db_type == 'postgresql' else {}
        engine = create_engine(uri, **kwargs)
        with engine.connect() as conn:
            conn.execute(text('SELECT 1'))
        engine.dispose()
        return jsonify({'ok': True, 'message': 'Connection successful.'})
    except Exception as exc:
        return jsonify({'ok': False, 'message': str(exc)}), 400


@setup_bp.route('/complete', methods=['POST'])
def complete():
    from app.models import User
    if User.query.count() > 0:
        return jsonify({'error': 'Setup already completed'}), 403

    data = request.get_json() or {}

    setup_type = data.get('setup_type', 'fresh')   # 'fresh' | 'migration'
    master_key = (data.get('master_key') or '').strip()
    db_type    = data.get('db_type', 'sqlite')
    ssl_mode   = data.get('ssl_mode', 'http')

    errors = {}

    # Master key validation
    if not master_key:
        errors['master_key'] = 'Master key is required.'
    elif not EncryptionManager.verify_key_format(master_key):
        # For migration with "existing" key source, give a clearer message
        src = data.get('master_key_source', 'new')
        errors['master_key'] = (
            'This does not look like a valid Fernet key. '
            'Check you copied the full key from your original instance.'
            if src == 'existing' else
            'Invalid Fernet key format. Use the Generate button.'
        )

    # Admin fields only required for fresh installs
    username = (data.get('username') or '').strip()
    email    = (data.get('email') or '').strip()
    password = (data.get('password') or '')
    confirm  = (data.get('confirm_password') or '')
    if setup_type == 'fresh':
        if not username or len(username) < 3:
            errors['username'] = 'At least 3 characters required.'
        if not email or '@' not in email:
            errors['email'] = 'Enter a valid email address.'
        if not password or len(password) < 8:
            errors['password'] = 'At least 8 characters required.'
        elif password != confirm:
            errors['confirm_password'] = 'Passwords do not match.'

    if errors:
        return jsonify({'errors': errors}), 422

    # SSL: generate or validate cert files
    ssl_cert_path = ''
    ssl_key_path  = ''
    if ssl_mode == 'self-signed':
        cert_cn       = (data.get('cert_cn') or 'ConfigLake').strip()
        cert_org      = (data.get('cert_org') or '').strip()
        cert_ou       = (data.get('cert_ou') or '').strip()
        cert_validity = max(1, min(int(data.get('cert_validity_years') or 1), 5))
        try:
            ssl_cert_path, ssl_key_path = _generate_self_signed_cert(
                cn=cert_cn, org=cert_org, ou=cert_ou,
                validity_days=cert_validity * 365,
            )
        except Exception as exc:
            return jsonify({'errors': {'ssl': f'Could not generate certificate: {exc}'}}), 500
    elif ssl_mode == 'manual':
        ssl_cert_content = (data.get('ssl_cert_content') or '').strip()
        ssl_key_content  = (data.get('ssl_key_content') or '').strip()
        if not ssl_cert_content or not ssl_key_content:
            return jsonify({'errors': {'ssl': 'Both certificate and private key content are required.'}}), 422
        if '-----BEGIN' not in ssl_cert_content:
            return jsonify({'errors': {'ssl': 'Certificate does not appear to be in PEM format.'}}), 422
        if '-----BEGIN' not in ssl_key_content:
            return jsonify({'errors': {'ssl': 'Private key does not appear to be in PEM format.'}}), 422
        try:
            ssl_cert_path, ssl_key_path = _save_cert_content(ssl_cert_content, ssl_key_content)
        except Exception as exc:
            return jsonify({'errors': {'ssl': f'Could not save certificate: {exc}'}}), 500

    # Persist all settings to .env
    _write_env('CONFIGLAKE_MASTER_KEY', master_key)
    db_uri = _build_db_uri(data)
    if db_type != 'sqlite':
        _write_env('DATABASE_URL', db_uri)
    if ssl_mode in ('self-signed', 'manual'):
        _write_env('SSL_MODE', ssl_mode)
        _write_env('SSL_CERT_PATH', ssl_cert_path)
        _write_env('SSL_KEY_PATH', ssl_key_path)
    elif ssl_mode == 'proxy':
        _write_env('SSL_MODE', 'proxy')

    # Initialise the database and create the admin user (fresh only)
    restart_required = False
    try:
        if setup_type == 'fresh':
            if db_type == 'sqlite':
                from app import db
                db.create_all()
                _create_admin_orm(username, email, password)
            else:
                restart_required = True
                _init_remote_db(db_uri, username, email, password)
        else:
            # Migration: create/upgrade schema only, no admin creation
            restart_required = True
            if db_type == 'sqlite':
                from app import db
                from sqlalchemy import inspect, text
                db.create_all()
                inspector = inspect(db.engine)
                cols = [c['name'] for c in inspector.get_columns('environment')]
                if 'key_is_wrapped' not in cols:
                    with db.engine.connect() as conn:
                        conn.execute(text(
                            'ALTER TABLE environment ADD COLUMN key_is_wrapped BOOLEAN NOT NULL DEFAULT 0'
                        ))
                        conn.commit()
            else:
                _migrate_remote_db(db_uri)
    except Exception as exc:
        logger.exception('Setup DB init failed.')
        return jsonify({'error': f'Database initialisation failed: {exc}'}), 500

    logger.info("Setup completed (type=%s, db=%s, ssl=%s).", setup_type, db_type, ssl_mode)
    session['setup_restart_token'] = True  # authorises exactly one restart via /setup/restart
    return jsonify({
        'ok': True,
        'over_http': request.scheme == 'http' and ssl_mode == 'http',
        'restart_required': restart_required,
        'ssl_mode': ssl_mode,
    })


@setup_bp.route('/upload-db', methods=['POST'])
def upload_db():
    """Accept a SQLite .db file upload during migration setup."""
    err = _setup_only()
    if err:
        return err
    if 'file' not in request.files or not request.files['file'].filename:
        return jsonify({'error': 'No file provided'}), 400

    f = request.files['file']
    if not f.filename.lower().endswith('.db'):
        return jsonify({'error': 'Only .db files are accepted'}), 400

    from werkzeug.utils import secure_filename
    filename = secure_filename(f.filename)

    root         = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    instance_dir = os.path.join(root, 'instance')
    os.makedirs(instance_dir, exist_ok=True)

    dest = os.path.join(instance_dir, filename)
    f.save(dest)
    logger.info("Migration DB upload saved to %s", dest)
    return jsonify({'ok': True, 'path': dest, 'filename': filename})


@setup_bp.route('/restart', methods=['POST'])
def restart():
    """Signal the supervisor (app.py __main__) to restart the server.

    We exit with code 42 — the supervisor loop in app.py detects this,
    waits for the port to be released, then relaunches a fresh child.
    This avoids the 'Address already in use' race that os.execv causes.

    Requires the one-time session token set by /setup/complete so that
    random unauthenticated requests cannot trigger a restart after setup.
    """
    if not session.pop('setup_restart_token', False):
        return jsonify({'error': 'Not authorised'}), 403
    import threading

    def _do():
        import time
        time.sleep(1.0)   # let the HTTP response reach the browser first
        os._exit(42)      # hard-exit with restart code; supervisor relaunches

    threading.Thread(target=_do, daemon=False).start()
    return jsonify({'ok': True})


@setup_bp.route('/done')
def done():
    return render_template(
        'setup/done.html',
        over_http=request.args.get('over_http') == '1',
        restart_required=request.args.get('restart') == '1',
        ssl_mode=request.args.get('ssl_mode', 'http'),
    )


# ── Helpers ────────────────────────────────────────────────────────────────

def _build_db_uri(data):
    db_type = data.get('db_type', 'sqlite')
    if db_type == 'sqlite':
        path = (data.get('db_path') or '').strip() or 'configlake.db'
        return f'sqlite:///{path}'
    host = (data.get('db_host') or 'localhost').strip()
    port = (data.get('db_port') or ('5432' if db_type == 'postgresql' else '3306')).strip()
    user = (data.get('db_user') or '').strip()
    pwd  = (data.get('db_password') or '').strip()
    name = (data.get('db_name') or 'configlake').strip()
    if db_type == 'postgresql':
        return f'postgresql+psycopg2://{user}:{pwd}@{host}:{port}/{name}'
    return f'mysql+pymysql://{user}:{pwd}@{host}:{port}/{name}'


def _create_admin_orm(username, email, password):
    from app import db
    from app.models import User
    user = User(username=username, email=email, is_admin=True, is_approved=True)
    user.set_password(password)
    db.session.add(user)
    db.session.commit()


def _init_remote_db(db_uri, username, email, password):
    """Create tables and admin user in a remote DB using a temporary engine."""
    import bcrypt
    from sqlalchemy import create_engine, text
    from app import db

    engine = create_engine(db_uri)
    db.metadata.create_all(engine)

    password_hash = bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    with engine.connect() as conn:
        conn.execute(text(
            'INSERT INTO "user" (username, email, password_hash, is_admin, is_approved, created_at) '
            'VALUES (:username, :email, :password_hash, :is_admin, :is_approved, :created_at)'
        ), {
            'username': username, 'email': email,
            'password_hash': password_hash, 'is_admin': True, 'is_approved': True,
            'created_at': datetime.datetime.utcnow(),
        })
        conn.commit()
    engine.dispose()


def _migrate_remote_db(db_uri):
    """Create missing tables and add new columns to an existing remote DB (safe to run on any data)."""
    from sqlalchemy import create_engine, inspect, text
    from app import db

    engine = create_engine(db_uri)
    db.metadata.create_all(engine)          # no-op for existing tables, creates new ones

    inspector = inspect(engine)
    if 'environment' in inspector.get_table_names():
        cols = [c['name'] for c in inspector.get_columns('environment')]
        if 'key_is_wrapped' not in cols:
            with engine.connect() as conn:
                conn.execute(text(
                    'ALTER TABLE environment ADD COLUMN key_is_wrapped BOOLEAN NOT NULL DEFAULT 0'
                ))
                conn.commit()
    engine.dispose()


def _save_cert_content(cert_pem: str, key_pem: str):
    """Write pasted PEM content to certs/ and return (cert_path, key_path)."""
    root      = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    certs_dir = os.path.join(root, 'certs')
    os.makedirs(certs_dir, exist_ok=True)
    cert_path = os.path.join(certs_dir, 'cert.pem')
    key_path  = os.path.join(certs_dir, 'key.pem')
    with open(cert_path, 'w') as f:
        f.write(cert_pem if cert_pem.endswith('\n') else cert_pem + '\n')
    with open(key_path, 'w') as f:
        f.write(key_pem if key_pem.endswith('\n') else key_pem + '\n')
    return cert_path, key_path


def _generate_self_signed_cert(cn='ConfigLake', org='', ou='', validity_days=3650):
    from cryptography import x509
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from cryptography.x509.oid import NameOID

    root      = os.path.dirname(os.path.dirname(os.path.dirname(__file__)))
    certs_dir = os.path.join(root, 'certs')
    os.makedirs(certs_dir, exist_ok=True)
    cert_path = os.path.join(certs_dir, 'cert.pem')
    key_path  = os.path.join(certs_dir, 'key.pem')

    name_attrs = [x509.NameAttribute(NameOID.COMMON_NAME, cn)]
    if org:
        name_attrs.append(x509.NameAttribute(NameOID.ORGANIZATION_NAME, org))
    if ou:
        name_attrs.append(x509.NameAttribute(NameOID.ORGANIZATIONAL_UNIT_NAME, ou))
    name = x509.Name(name_attrs)

    key  = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    now  = datetime.datetime.utcnow()
    cert = (
        x509.CertificateBuilder()
        .subject_name(name).issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(now)
        .not_valid_after(now + datetime.timedelta(days=validity_days))
        .add_extension(x509.SubjectAlternativeName([
            x509.DNSName('localhost'),
            x509.IPAddress(ipaddress.IPv4Address('127.0.0.1')),
        ]), critical=False)
        .sign(key, hashes.SHA256())
    )

    with open(cert_path, 'wb') as f:
        f.write(cert.public_bytes(serialization.Encoding.PEM))
    with open(key_path, 'wb') as f:
        f.write(key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        ))
    return cert_path, key_path


def _write_env(key: str, value: str):
    """Write or update a single key=value in the project-root .env file."""
    env_path = os.path.join(
        os.path.dirname(os.path.dirname(os.path.dirname(__file__))), '.env'
    )
    new_line = f'{key}={value}\n'
    if os.path.exists(env_path):
        with open(env_path) as f:
            lines = f.readlines()
        updated = False
        for i, line in enumerate(lines):
            if line.startswith(f'{key}='):
                lines[i] = new_line
                updated   = True
                break
        if not updated:
            lines.append(new_line)
        with open(env_path, 'w') as f:
            f.writelines(lines)
    else:
        with open(env_path, 'w') as f:
            f.write(new_line)
