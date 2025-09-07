import ipaddress
import socket
import re
from functools import wraps
from flask import request, jsonify, g
from flask_login import current_user
from app.models import AllowedIP, ProjectUser, APIToken
from datetime import datetime

def check_ip_whitelist(project_id, environment_id=None):
    """Check if the client IP is whitelisted for the project or environment."""
    client_ip = request.environ.get('HTTP_X_FORWARDED_FOR') or request.remote_addr
    
    # Get allowed IPs for the project
    query = AllowedIP.query.filter_by(project_id=project_id)
    
    # Check if environment_id column exists (for backward compatibility)
    try:
        if environment_id and hasattr(AllowedIP, 'environment_id'):
            # New version: Check both project-wide and environment-specific IPs
            allowed_ips = query.filter(
                (AllowedIP.environment_id == environment_id) | 
                (AllowedIP.environment_id == None)
            ).all()
        else:
            # Fallback for older database schema
            allowed_ips = query.all()
    except Exception:
        # Fallback to old behavior if column doesn't exist
        allowed_ips = query.all()
    
    # If no IPs are configured, deny access (production behavior)
    if not allowed_ips:
        return False
    
    try:
        client_ip_obj = ipaddress.ip_address(client_ip)
        
        for allowed_ip in allowed_ips:
            try:
                # Handle IP:port format - extract just the IP part for comparison
                import re
                port_pattern = r'^(.+):(\d+)$'
                port_match = re.match(port_pattern, allowed_ip.ip_address)
                
                if port_match:
                    # Extract just the IP/hostname part
                    host_part = port_match.group(1)
                    
                    # Check if it's an FQDN
                    if getattr(allowed_ip, 'is_fqdn', False):
                        try:
                            resolved_ips = socket.getaddrinfo(host_part, None)
                            for addr_info in resolved_ips:
                                resolved_ip = ipaddress.ip_address(addr_info[4][0])
                                if client_ip_obj == resolved_ip:
                                    return True
                        except (socket.gaierror, ValueError):
                            continue
                    # Check if it's a network range or single IP
                    elif '/' in host_part:
                        network = ipaddress.ip_network(host_part, strict=False)
                        if client_ip_obj in network:
                            return True
                    else:
                        try:
                            allowed_ip_obj = ipaddress.ip_address(host_part)
                            if client_ip_obj == allowed_ip_obj:
                                return True
                        except ValueError:
                            # Try as hostname
                            try:
                                resolved_ips = socket.getaddrinfo(host_part, None)
                                for addr_info in resolved_ips:
                                    resolved_ip = ipaddress.ip_address(addr_info[4][0])
                                    if client_ip_obj == resolved_ip:
                                        return True
                            except (socket.gaierror, ValueError):
                                continue
                else:
                    # Original logic for entries without port
                    # Check if it's an FQDN
                    if getattr(allowed_ip, 'is_fqdn', False):
                        # Resolve FQDN to IP addresses
                        try:
                            resolved_ips = socket.getaddrinfo(allowed_ip.ip_address, None)
                            for addr_info in resolved_ips:
                                resolved_ip = ipaddress.ip_address(addr_info[4][0])
                                if client_ip_obj == resolved_ip:
                                    return True
                        except (socket.gaierror, ValueError):
                            continue
                    # Check if it's a network range or single IP
                    elif '/' in allowed_ip.ip_address:
                        network = ipaddress.ip_network(allowed_ip.ip_address, strict=False)
                        if client_ip_obj in network:
                            return True
                    else:
                        allowed_ip_obj = ipaddress.ip_address(allowed_ip.ip_address)
                        if client_ip_obj == allowed_ip_obj:
                            return True
            except ValueError:
                continue
        
        return False
    except ValueError:
        return False

def require_project_permission(required_role='reader'):
    """Decorator to check if user has required permissions for a project (NO IP restrictions for dashboard)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            project_id = kwargs.get('project_id') or request.view_args.get('project_id')
            
            if not project_id:
                return jsonify({'error': 'Project ID required'}), 400
            
            # NO IP whitelist check for dashboard/management interfaces
            
            # Check user permissions
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401
            
            # Admin users have access to all projects
            if current_user.is_admin:
                g.user_role = 'owner'
                return f(*args, **kwargs)
            
            project_user = ProjectUser.query.filter_by(
                user_id=current_user.id,
                project_id=project_id
            ).first()
            
            if not project_user:
                return jsonify({'error': 'Access denied: Not a project member'}), 403
            
            # Check role hierarchy: owner > maintainer > reader
            role_hierarchy = {'owner': 3, 'maintainer': 2, 'reader': 1}
            user_level = role_hierarchy.get(project_user.role, 0)
            required_level = role_hierarchy.get(required_role, 0)
            
            if user_level < required_level:
                return jsonify({'error': f'Access denied: {required_role} role required'}), 403
            
            g.user_role = project_user.role
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def require_project_permission_with_ip(required_role='reader'):
    """Decorator to check user permissions AND IP whitelist (for client API endpoints)."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            project_id = kwargs.get('project_id') or request.view_args.get('project_id')
            
            if not project_id:
                return jsonify({'error': 'Project ID required'}), 400
            
            # Check IP whitelist for client API endpoints  
            if not check_ip_whitelist(project_id):
                return jsonify({'error': 'Access denied: IP not whitelisted'}), 403
            
            # Check user permissions
            if not current_user.is_authenticated:
                return jsonify({'error': 'Authentication required'}), 401
            
            # Admin users have access to all projects
            if current_user.is_admin:
                g.user_role = 'owner'
                return f(*args, **kwargs)
            
            project_user = ProjectUser.query.filter_by(
                user_id=current_user.id,
                project_id=project_id
            ).first()
            
            if not project_user:
                return jsonify({'error': 'Access denied: Not a project member'}), 403
            
            # Check role hierarchy: owner > maintainer > reader
            role_hierarchy = {'owner': 3, 'maintainer': 2, 'reader': 1}
            user_level = role_hierarchy.get(project_user.role, 0)
            required_level = role_hierarchy.get(required_role, 0)
            
            if user_level < required_level:
                return jsonify({'error': f'Access denied: {required_role} role required'}), 403
            
            g.user_role = project_user.role
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def require_api_token():
    """Decorator to validate API token for external API access."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            auth_header = request.headers.get('Authorization')
            
            if not auth_header or not auth_header.startswith('Bearer '):
                return jsonify({'error': 'API token required'}), 401
            
            token = auth_header.split(' ')[1]
            
            api_token = APIToken.query.filter_by(
                token=token,
                is_active=True
            ).first()
            
            if not api_token:
                return jsonify({'error': 'Invalid API token'}), 401
            
            # Check if token is expired
            if api_token.expires_at < datetime.utcnow():
                return jsonify({'error': 'API token expired'}), 401
            
            # Check IP whitelist for the project and environment
            if not check_ip_whitelist(api_token.project_id, api_token.environment_id):
                return jsonify({'error': 'Access denied: IP not whitelisted'}), 403
            
            g.api_token = api_token
            return f(*args, **kwargs)
        
        return decorated_function
    return decorator

def check_origin_whitelist(origin, project_id, environment_id=None):
    """Check if the origin is whitelisted for the project or environment (for CORS)."""
    if not origin:
        return False
    
    # Get allowed IPs for the project
    query = AllowedIP.query.filter_by(project_id=project_id)
    
    # Check if environment_id column exists (for backward compatibility)
    try:
        if environment_id and hasattr(AllowedIP, 'environment_id'):
            # New version: Check both project-wide and environment-specific IPs
            allowed_ips = query.filter(
                (AllowedIP.environment_id == environment_id) | 
                (AllowedIP.environment_id == None)
            ).all()
        else:
            # Fallback for older database schema
            allowed_ips = query.all()
    except Exception:
        # Fallback to old behavior if column doesn't exist
        allowed_ips = query.all()
    
    # If no IPs are configured, deny access
    if not allowed_ips:
        return False
    
    # Extract hostname and port from origin (e.g., "http://localhost:3000")
    origin_pattern = r'^https?://([^:/]+)(?::(\d+))?'
    origin_match = re.match(origin_pattern, origin)
    
    if not origin_match:
        return False
    
    origin_host = origin_match.group(1)
    origin_port = origin_match.group(2)
    
    # Check against whitelist entries
    for allowed_ip in allowed_ips:
        try:
            # Handle different formats in whitelist:
            # 1. "http://localhost:3000" - full URL format
            # 2. "localhost:3000" - host:port format  
            # 3. "localhost" - just hostname
            # 4. "10.21.81.126:3000" - IP:port format
            # 5. "10.21.81.126" - just IP
            
            allowed_entry = allowed_ip.ip_address.strip()
            
            # Check if it's a full URL (starts with http/https)
            if allowed_entry.startswith(('http://', 'https://')):
                if origin == allowed_entry:
                    return True
                continue
            
            # Handle host:port format
            port_pattern = r'^(.+):(\d+)$'
            port_match = re.match(port_pattern, allowed_entry)
            
            if port_match:
                allowed_host = port_match.group(1)
                allowed_port = port_match.group(2)
                
                # Check if both host and port match
                if origin_host == allowed_host and origin_port == allowed_port:
                    return True
            else:
                # Just hostname/IP - check if host matches (ignoring port)
                if origin_host == allowed_entry:
                    return True
        
        except Exception:
            continue
    
    return False