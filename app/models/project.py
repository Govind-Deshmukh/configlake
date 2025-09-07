from datetime import datetime
from app import db

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    environments = db.relationship('Environment', back_populates='project', cascade='all, delete-orphan')
    project_users = db.relationship('ProjectUser', back_populates='project', cascade='all, delete-orphan')
    allowed_ips = db.relationship('AllowedIP', back_populates='project', cascade='all, delete-orphan')