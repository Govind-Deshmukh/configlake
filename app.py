from app import create_app, db
from app.models import User, Project, Environment, Config, Secret, ProjectUser, AllowedIP, APIToken
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

if __name__ == '__main__':
    if len(sys.argv) > 1:
        command = sys.argv[1]
        
        if command == 'init-db':
            init_db()
        elif command == 'create-admin':
            create_admin()
        else:
            print("Available commands:")
            print("  python app.py init-db     - Initialize the database")
            print("  python app.py create-admin - Create an admin user")
            print("  python app.py             - Start the web server")
    else:
        # Start the web server
        port = int(os.environ.get('PORT', 5000))
        debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
        app.run(host='0.0.0.0', port=port, debug=debug)