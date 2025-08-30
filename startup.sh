#!/bin/bash

# Check if database has any users and run setup if empty
python3 -c "
from app import create_app, db
from app.models import User

app = create_app()
with app.app_context():
    db.create_all()
    user_count = User.query.count()
    if user_count == 0:
        print('No users found. Creating default admin user...')
        admin_user = User(username='admin', email='admin@configlake.local', is_admin=True)
        admin_user.set_password('admin1234')
        db.session.add(admin_user)
        db.session.commit()
        print('Default admin user created (admin:admin1234)')
    else:
        print(f'Database has {user_count} users. Skipping admin creation.')
"

# Start the application
python app.py