from datetime import datetime
from app import db

class Config(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(100), nullable=False)
    value = db.Column(db.Text, nullable=False)
    environment_id = db.Column(db.Integer, db.ForeignKey('environment.id'), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    environment = db.relationship('Environment', back_populates='configs')
    
    __table_args__ = (db.UniqueConstraint('key', 'environment_id', name='unique_config_per_env'),)