from datetime import datetime
from app import db

class Secret(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False)
    encrypted_value = db.Column(db.Text, nullable=False)  # Encrypted secret value
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    environment = db.relationship('Environment', back_populates='secrets')
    
    __table_args__ = (db.UniqueConstraint('key', 'environment_id', name='unique_secret_per_env'),)