from datetime import datetime
from app import db

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