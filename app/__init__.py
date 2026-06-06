from flask import Flask, redirect, request, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_cors import CORS
from flask_wtf.csrf import CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix
from config import Config

db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()

def create_app():
    app = Flask(__name__)
    app.config.from_object(Config)

    # Trust X-Forwarded-Proto and X-Forwarded-For from a single upstream proxy
    # so request.scheme reflects https when Nginx/Caddy terminates TLS.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1, x_for=1)

    # Configure CORS to handle all requests
    CORS(app, origins=[], supports_credentials=True)

    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    login_manager.login_view = 'auth.login'

    from app.models import User

    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    from app.routes.auth import auth_bp
    from app.routes.projects import projects_bp
    from app.routes.api import api_bp
    from app.routes.main import main_bp
    from app.routes.setup import setup_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(projects_bp, url_prefix='/projects')
    app.register_blueprint(api_bp, url_prefix='/api')
    app.register_blueprint(main_bp)
    app.register_blueprint(setup_bp, url_prefix='/setup')

    # API endpoints use Bearer tokens; setup has its own _setup_only() guard.
    csrf.exempt(api_bp)
    csrf.exempt(setup_bp)

    # Auto-init and migrate after all models are registered with the metadata.
    with app.app_context():
        db.create_all()
        _auto_migrate(app)

    @app.before_request
    def redirect_to_setup_if_needed():
        # Allow setup routes and static files to pass through unconditionally.
        if request.endpoint and (
            request.endpoint.startswith('setup.')
            or request.endpoint == 'static'
        ):
            return None

        # If no admin user exists yet, send everything to the setup wizard.
        from app.models import User
        if User.query.count() == 0:
            return redirect(url_for('setup.index'))
    
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


def _auto_migrate(app):
    """Add columns introduced in upgrades to an existing database (idempotent)."""
    from sqlalchemy import inspect, text
    try:
        inspector = inspect(db.engine)
        columns = [col['name'] for col in inspector.get_columns('environment')]
        if 'key_is_wrapped' not in columns:
            with db.engine.connect() as conn:
                conn.execute(text(
                    'ALTER TABLE environment ADD COLUMN key_is_wrapped BOOLEAN NOT NULL DEFAULT 0'
                ))
                conn.commit()
            app.logger.info("DB migration: added 'key_is_wrapped' column.")
    except Exception:
        pass  # Table doesn't exist yet — db.create_all() just ran or will handle it