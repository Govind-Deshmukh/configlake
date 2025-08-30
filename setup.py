#!/usr/bin/env python3
"""
Setup script for ConfigLake
This script initializes the database and creates an admin user.
"""

import sys
import getpass
from app import create_app, db
from app.models import User

def init_database():
    """Initialize the database."""
    print("Initializing database...")
    db.create_all()
    print("Database initialized!")

def create_admin_user():
    """Create an admin user."""
    print("\n=== Create Admin User ===")
    
    username = input("Enter admin username: ").strip()
    if not username:
        print("❌ Username is required!")
        return False
    
    email = input("Enter admin email: ").strip()
    if not email:
        print("❌ Email is required!")
        return False
    
    password = getpass.getpass("Enter admin password: ")
    if not password:
        print("❌ Password is required!")
        return False
    
    confirm_password = getpass.getpass("Confirm password: ")
    if password != confirm_password:
        print("❌ Passwords do not match!")
        return False
    
    if len(password) < 8:
        print("❌ Password must be at least 8 characters long!")
        return False
    
    # Check if user already exists
    existing_user = User.query.filter(
        (User.username == username) | (User.email == email)
    ).first()
    
    if existing_user:
        print(f"❌ User with username '{username}' or email '{email}' already exists!")
        return False
    
    # Create admin user
    admin_user = User(username=username, email=email, is_admin=True)
    admin_user.set_password(password)
    
    db.session.add(admin_user)
    db.session.commit()
    
    print(f"Admin user '{username}' created successfully!")
    print(f"📧 Email: {email}")
    print("🔐 You can now login with these credentials")
    return True

def main():
    """Main setup function."""
    print("🚀 ConfigLake Setup")
    print("=" * 30)
    
    app = create_app()
    
    with app.app_context():
        # Initialize database
        init_database()
        
        # Create admin user
        if not create_admin_user():
            print("\n❌ Setup failed!")
            sys.exit(1)
        
        print(f"\n🎉 Setup completed successfully!")
        print(f"🌐 Start the application with: python app.py")
        print(f"📱 Access at: http://localhost:5000")

if __name__ == "__main__":
    main()