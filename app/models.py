from datetime import datetime
from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from app import db

class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    project_users = db.relationship('ProjectUser', back_populates='user', cascade='all, delete-orphan')
    
    def set_password(self, password):
        self.password_hash = generate_password_hash(password)
    
    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

class Project(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    description = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    environments = db.relationship('Environment', back_populates='project', cascade='all, delete-orphan')
    project_users = db.relationship('ProjectUser', back_populates='project', cascade='all, delete-orphan')
    allowed_ips = db.relationship('AllowedIP', back_populates='project', cascade='all, delete-orphan')

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

class ProjectUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='reader')  # owner, maintainer, reader
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='project_users')
    project = db.relationship('Project', back_populates='project_users')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'project_id', name='unique_user_per_project'),)

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Text, nullable=False)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    environment = db.relationship('Environment', back_populates='configs')
    
    __table_args__ = (db.UniqueConstraint('key', 'environment_id', name='unique_config_per_env'),)

class Secret(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False)
    encrypted_value = db.Column(db.Text, nullable=False)  # Encrypted secret value
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    environment = db.relationship('Environment', back_populates='secrets')
    
    __table_args__ = (db.UniqueConstraint('key', 'environment_id', name='unique_secret_per_env'),)

class AllowedIP(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    ip_address = db.Column(db.String(255), nullable=False)  # Support IPv6, CIDR, and FQDN
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=True)  # NULL = project-wide, specific = environment-specific
    description = db.Column(db.String(200))
    is_fqdn = db.Column(db.Boolean, default=False)  # True if this is an FQDN instead of IP
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    project = db.relationship('Project', back_populates='allowed_ips')
    environment = db.relationship('Environment', overlaps="allowed_ips")

class APIToken(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    token = db.Column(db.String(255), unique=True, nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    name = db.Column(db.String(100), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    expires_at = db.Column(db.DateTime, nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    
    project = db.relationship('Project')
    environment = db.relationship('Environment')

