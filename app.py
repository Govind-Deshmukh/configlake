from app import create_app, db
from app.models import User, Project, Environment, Config, Secret, ProjectUser, AllowedIP, APIToken
import os

app = create_app()

@app.cli.command()
def init_db():
    """Initialize the database."""
    with app.app_context():
        db.create_all()
        print("Database initialized!")

@app.cli.command()
def create_admin():
    """Create an admin user."""
    username = input("Admin username: ")
    email = input("Admin email: ")
    password = input("Admin password: ")
    
    with app.app_context():
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
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'True').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)