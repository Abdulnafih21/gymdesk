from functools import wraps
from flask import redirect, url_for, flash, abort
from flask_login import current_user


def role_required(*roles):
    """Decorator to restrict access to specific user roles."""
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not current_user.is_authenticated:
                flash('Please log in to access this page.', 'warning')
                return redirect(url_for('auth.login'))
            if current_user.role not in roles:
                abort(403)
            return f(*args, **kwargs)
        return decorated_function
    return decorator


def gym_admin_required(f):
    """Shortcut decorator for gym admin access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if current_user.role not in ('gym_admin', 'system_admin'):
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def trainer_required(f):
    """Shortcut decorator for trainer access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if current_user.role != 'trainer':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function


def member_required(f):
    """Shortcut decorator for member access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not current_user.is_authenticated:
            flash('Please log in to access this page.', 'warning')
            return redirect(url_for('auth.login'))
        if current_user.role != 'member':
            abort(403)
        return f(*args, **kwargs)
    return decorated_function
