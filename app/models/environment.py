from datetime import datetime
from app import db

class Environment(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(50), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    secret_key = db.Column(db.String(255), nullable=False)  # Environment-specific encryption key
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    project = db.relationship('Project', back_populates='environments')
    configs = db.relationship('Config', back_populates='environment', cascade='all, delete-orphan')
    secrets = db.relationship('Secret', back_populates='environment', cascade='all, delete-orphan')
    allowed_ips = db.relationship('AllowedIP', cascade='all, delete-orphan')
    
    __table_args__ = (db.UniqueConstraint('name', 'project_id', name='unique_env_per_project'),)