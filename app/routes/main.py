from flask import Blueprint, render_template, redirect, url_for, request, flash
from flask_login import login_required, current_user
from app.models import Project, ProjectUser, User
from app import db

main_bp = Blueprint('main', __name__)

@main_bp.route('/')
def index():
    if current_user.is_authenticated:
        return redirect(url_for('main.dashboard'))
    return redirect(url_for('auth.login'))

@main_bp.route('/dashboard')
@login_required
def dashboard():
    if current_user.is_admin:
        projects = Project.query.all()
    else:
        project_users = ProjectUser.query.filter_by(user_id=current_user.id).all()
        projects = [pu.project for pu in project_users]
    
    return render_template('dashboard.html', projects=projects)

@main_bp.route('/admin/users')
@login_required
def admin_users():
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    users = User.query.all()
    
    # Get user statistics
    user_stats = []
    for user in users:
        project_count = ProjectUser.query.filter_by(user_id=user.id).count()
        owned_projects = ProjectUser.query.filter_by(user_id=user.id, role='owner').count()
        user_stats.append({
            'user': user,
            'project_count': project_count,
            'owned_projects': owned_projects
        })
    
    return render_template('admin/users.html', user_stats=user_stats)

@main_bp.route('/admin/users/<int:user_id>/toggle_admin', methods=['POST'])
@login_required
def toggle_admin(user_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    if user_id == current_user.id:
        flash('Cannot change your own admin status', 'error')
        return redirect(url_for('main.admin_users'))
    
    user = User.query.get_or_404(user_id)
    user.is_admin = not user.is_admin
    db.session.commit()
    
    status = 'granted' if user.is_admin else 'revoked'
    flash(f"Admin privileges {status} for user '{user.username}'", 'success')
    return redirect(url_for('main.admin_users'))

@main_bp.route('/admin/users/<int:user_id>/delete', methods=['POST'])
@login_required
def delete_user(user_id):
    if not current_user.is_admin:
        flash('Access denied. Admin privileges required.', 'error')
        return redirect(url_for('main.dashboard'))
    
    if user_id == current_user.id:
        flash('Cannot delete your own account', 'error')
        return redirect(url_for('main.admin_users'))
    
    user = User.query.get_or_404(user_id)
    
    # Check if user is the sole owner of any projects
    sole_owner_projects = []
    owned_projects = ProjectUser.query.filter_by(user_id=user_id, role='owner').all()
    
    for project_user in owned_projects:
        owner_count = ProjectUser.query.filter_by(
            project_id=project_user.project_id,
            role='owner'
        ).count()
        if owner_count == 1:
            sole_owner_projects.append(project_user.project.name)
    
    if sole_owner_projects:
        flash(f"Cannot delete user. They are the sole owner of: {', '.join(sole_owner_projects)}", 'error')
        return redirect(url_for('main.admin_users'))
    
    username = user.username
    db.session.delete(user)
    db.session.commit()
    
    flash(f"User '{username}' has been deleted", 'success')
    return redirect(url_for('main.admin_users'))