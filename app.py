from app import create_app, db
from app.models import User, Project, Environment, Config, Secret, ProjectUser, AllowedIP, APIToken
from app.utils.encryption import EncryptionManager
import argparse
import os
import sys

app = create_app()

def init_db():
    """Initialize the database."""
    with app.app_context():
        db.create_all()
        print("Database initialized!")

def create_admin():
    """Create an admin user."""
    with app.app_context():
        username = input("Admin username: ")
        email = input("Admin email: ")
        password = input("Admin password: ")
        
        existing_user = User.query.filter(
            (User.username == username) | (User.email == email)
        ).first()
        
        if existing_user:
            print("User already exists!")
            return
        
        admin_user = User(username=username, email=email, is_admin=True)
        admin_user.set_password(password)
        
        db.session.add(admin_user)
        db.session.commit()
        
        print(f"Admin user '{username}' created successfully!")

def migrate_db():
    """Add columns introduced in upgrades to an existing database."""
    with app.app_context():
        from sqlalchemy import text, inspect
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('environment')]

        if 'key_is_wrapped' not in columns:
            with db.engine.connect() as conn:
                conn.execute(text(
                    'ALTER TABLE environment ADD COLUMN key_is_wrapped BOOLEAN NOT NULL DEFAULT 0'
                ))
                conn.commit()
            print("Added 'key_is_wrapped' column to environment table.")
        else:
            print("Database schema is already up to date.")


def wrap_keys():
    """Wrap all plaintext environment keys with CONFIGLAKE_MASTER_KEY (envelope encryption)."""
    with app.app_context():
        master_key = os.environ.get('CONFIGLAKE_MASTER_KEY')
        if not master_key:
            print("Error: CONFIGLAKE_MASTER_KEY environment variable is not set.")
            sys.exit(1)

        if not EncryptionManager.verify_key_format(master_key):
            print("Error: CONFIGLAKE_MASTER_KEY is not a valid Fernet key.")
            sys.exit(1)

        environments = Environment.query.filter_by(key_is_wrapped=False).all()
        if not environments:
            print("All environment keys are already wrapped. Nothing to do.")
            return

        count = 0
        for env in environments:
            env.secret_key = EncryptionManager.wrap_env_key(env.secret_key, master_key)
            env.key_is_wrapped = True
            count += 1

        db.session.commit()
        print(f"Successfully wrapped {count} environment key(s).")


COMMANDS = {'init-db', 'create-admin', 'migrate-db', 'wrap-keys'}


def _run_server(argv):
    parser = argparse.ArgumentParser(
        prog='python app.py',
        description='Start the ConfigLake web server.',
    )
    parser.add_argument(
        '--ssl',
        action='store_true',
        help='Enable HTTPS with a self-signed certificate (requires pyOpenSSL).',
    )
    parser.add_argument(
        '--ssl-cert',
        metavar='CERT',
        help='Path to a PEM certificate file for HTTPS.',
    )
    parser.add_argument(
        '--ssl-key',
        metavar='KEY',
        help='Path to the corresponding PEM private key file.',
    )
    args = parser.parse_args(argv)

    ssl_context = None
    if args.ssl_cert and args.ssl_key:
        ssl_context = (args.ssl_cert, args.ssl_key)
        print(f"SSL: using provided certificate ({args.ssl_cert})")
    elif args.ssl:
        ssl_context = 'adhoc'
        print("SSL: auto-generated self-signed certificate (dev mode).")
        print("Your browser will show a security warning — accept it to proceed.")
    else:
        # Read SSL config written by the setup wizard
        ssl_mode = os.environ.get('SSL_MODE', '')
        ssl_cert = os.environ.get('SSL_CERT_PATH', '')
        ssl_key  = os.environ.get('SSL_KEY_PATH', '')
        if ssl_mode in ('self-signed', 'manual') and ssl_cert and ssl_key:
            if os.path.isfile(ssl_cert) and os.path.isfile(ssl_key):
                ssl_context = (ssl_cert, ssl_key)
                print(f"SSL: using certificate from setup configuration ({ssl_cert})")
            else:
                print(f"Warning: SSL_MODE={ssl_mode} but cert/key files not found. Running over HTTP.")
                print(f"  SSL_CERT_PATH={ssl_cert}")
                print(f"  SSL_KEY_PATH={ssl_key}")
        elif ssl_mode == 'proxy':
            print("HTTP: TLS terminated by reverse proxy — running plain HTTP internally.")
        else:
            print("HTTP: no SSL configured.")
            print("Run the setup wizard or use --ssl to enable HTTPS.")

    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug, ssl_context=ssl_context)


_RESTART_CODE = 42   # child exits with this code to request a restart


def _supervisor(argv):
    """
    Run the server as a child subprocess so a clean restart is possible.

    When the child exits with _RESTART_CODE the supervisor relaunches it.
    Any other exit code (0, 1, SIGINT …) propagates and the supervisor exits.

    This avoids the 'Address already in use' problem: the child process holds
    the socket; when it exits the OS releases the port before the new child
    starts.
    """
    import subprocess
    child_cmd = [sys.executable, __file__, '--_child'] + argv
    while True:
        try:
            result = subprocess.run(child_cmd)
        except KeyboardInterrupt:
            break
        if result.returncode != _RESTART_CODE:
            sys.exit(result.returncode)
        print('\nConfigLake is restarting…\n')


if __name__ == '__main__':
    # ── CLI commands (never need the supervisor loop) ──────────────────────
    if len(sys.argv) > 1 and not sys.argv[1].startswith('-'):
        command = sys.argv[1]
        if command == 'init-db':
            init_db()
        elif command == 'create-admin':
            create_admin()
        elif command == 'migrate-db':
            migrate_db()
        elif command == 'wrap-keys':
            wrap_keys()
        else:
            print("Available commands:")
            print("  python app.py init-db      - Initialize the database schema")
            print("  python app.py create-admin - Create an admin user")
            print("  python app.py migrate-db   - Add new columns to an existing database")
            print("  python app.py wrap-keys    - Encrypt all environment keys with CONFIGLAKE_MASTER_KEY")
            print()
            print("Server flags:")
            print("  python app.py              - Start over HTTP")
            print("  python app.py --ssl        - Start with a self-signed certificate (dev)")
            print("  python app.py --ssl-cert cert.pem --ssl-key key.pem  - Start with your own cert")

    # ── Internal child flag: actually run Flask (spawned by supervisor) ────
    elif '--_child' in sys.argv:
        child_argv = [a for a in sys.argv[1:] if a != '--_child']
        _run_server(child_argv)

    # ── Normal start: become the supervisor ───────────────────────────────
    else:
        _supervisor(sys.argv[1:])