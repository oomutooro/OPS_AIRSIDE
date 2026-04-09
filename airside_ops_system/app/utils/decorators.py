"""
Custom route decorators for role and permission checks.
"""
from functools import wraps
from flask import abort, flash, redirect, request, url_for
from flask_login import current_user, login_required


def role_required(*allowed_roles):
    """Require user to have one of the given roles."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login', next=request.url))

            if current_user.role not in allowed_roles and current_user.role != 'admin':
                if request.is_json:
                    abort(403)
                flash('You do not have permission to access this resource.', 'danger')
                return redirect(url_for('dashboard.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def permission_required(*permissions):
    """Require user to have all specified permissions."""
    def decorator(f):
        @wraps(f)
        @login_required
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                return redirect(url_for('auth.login', next=request.url))

            for permission in permissions:
                if not current_user.has_permission(permission):
                    if request.is_json:
                        abort(403)
                    flash(f'Permission denied: {permission}', 'danger')
                    return redirect(url_for('dashboard.index'))

            return f(*args, **kwargs)
        return decorated_function
    return decorator


def active_user_required(f):
    """Ensure the account is active before allowing access."""
    @wraps(f)
    @login_required
    def decorated_function(*args, **kwargs):
        if not current_user.is_active:
            flash('Your account is inactive. Contact administrator.', 'warning')
            return redirect(url_for('auth.logout'))
        return f(*args, **kwargs)
    return decorated_function
