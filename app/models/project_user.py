from datetime import datetime
from app import db

class ProjectUser(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    project_id = db.Column(db.Integer, db.ForeignKey('project.id'), nullable=False)
    role = db.Column(db.String(20), nullable=False, default='reader')  # owner, maintainer, reader
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    user = db.relationship('User', back_populates='project_users')
    project = db.relationship('Project', back_populates='project_users')
    
    __table_args__ = (db.UniqueConstraint('user_id', 'project_id', name='unique_user_per_project'),)