from flask import Flask, request
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_cors import CORS
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)
    
    # Configure CORS to handle all requests
    CORS(app, origins=[], supports_credentials=True)
    
    db.init_app(app)
    login_manager.init_app(app)
    login_manager.login_view = 'auth.login'
    
    from app.models import User
    
    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))
    
    from app.routes.auth import auth_bp
    from app.routes.projects import projects_bp
    from app.routes.api import api_bp
    from app.routes.main import main_bp
    
    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(projects_bp, url_prefix='/projects')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(main_bp)
    
    # Custom CORS handling for API endpoints with whitelist validation
    @app.after_request
    def after_request(response):
        origin = request.headers.get('Origin')
        
        # Only handle CORS for API endpoints
        if origin and request.endpoint and request.endpoint.startswith('api.'):
            # Import here to avoid circular imports
            from app.utils.security import check_origin_whitelist
            from app.models import APIToken
            import re
            
            # Extract project_id and environment from the API endpoint
            project_id = None
            environment_id = None
            
            # Try to get project_id from URL path
            path_match = re.search(r'/api/\w+/(\d+)/(\w+)', request.path)
            if path_match:
                project_id = int(path_match.group(1))
                environment_name = path_match.group(2)
                
                # Get environment_id from API token if available
                auth_header = request.headers.get('Authorization')
                if auth_header and auth_header.startswith('Bearer '):
                    token = auth_header.split(' ')[1]
                    api_token = APIToken.query.filter_by(token=token, is_active=True).first()
                    if api_token:
                        environment_id = api_token.environment_id
            
            # Check if origin is whitelisted for this project/environment
            if project_id and check_origin_whitelist(origin, project_id, environment_id):
                response.headers['Access-Control-Allow-Origin'] = origin
                response.headers['Access-Control-Allow-Headers'] = 'Authorization, Content-Type'
                response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
                response.headers['Access-Control-Allow-Credentials'] = 'true'
        
        return response
    
    return app