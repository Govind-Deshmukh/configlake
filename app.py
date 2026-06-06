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
        print(f"Starting ConfigLake with SSL certificate: {args.ssl_cert}")
    elif args.ssl:
        ssl_context = 'adhoc'
        print("Starting ConfigLake with a self-signed certificate (development only).")
        print("Your browser will show a security warning — accept it to proceed.")
    else:
        print("Starting ConfigLake over HTTP.")
        print("For production, terminate TLS at a reverse proxy (see deploy/).")

    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug, ssl_context=ssl_context)


if __name__ == '__main__':
    # Commands are plain positional words; server flags start with '--'.
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
            print("  python app.py create-admin - Create an admin user (CLI alternative to setup wizard)")
            print("  python app.py migrate-db   - Add new columns to an existing database")
            print("  python app.py wrap-keys    - Encrypt all environment keys with CONFIGLAKE_MASTER_KEY")
            print()
            print("Server flags (used without a command):")
            print("  python app.py              - Start over HTTP")
            print("  python app.py --ssl        - Start with a self-signed certificate (dev)")
            print("  python app.py --ssl-cert cert.pem --ssl-key key.pem  - Start with your own cert")
    else:
        _run_server(sys.argv[1:])