"""
Authentication routes: login, logout, profile, 2FA.
"""
from flask import Blueprint, flash, redirect, render_template, request, url_for
from flask_login import current_user, login_required, login_user, logout_user
from app import db, limiter
from app.models.user import User
from app.models.form import AuditLog

auth_bp = Blueprint('auth', __name__)


@auth_bp.route('/login', methods=['GET', 'POST'])
@limiter.limit('10 per minute')
def login():
    if current_user.is_authenticated:
        return redirect(url_for('dashboard.index'))

    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        password = request.form.get('password', '')
        remember = request.form.get('remember_me') == 'on'

        user = User.query.filter(
            (User.username == username) | (User.email == username)
        ).first()

        if user and user.check_password(password) and user.is_active:
            login_user(user, remember=remember)
            user.record_login()
            AuditLog.log('LOGIN', user_id=user.id, description='User logged in successfully.')
            db.session.commit()
            next_url = request.args.get('next')
            return redirect(next_url or url_for('dashboard.index'))

        flash('Invalid credentials or inactive account.', 'danger')

    return render_template('auth/login.html')


@auth_bp.route('/logout')
@login_required
def logout():
    AuditLog.log('LOGOUT', user_id=current_user.id, description='User logged out.')
    db.session.commit()
    logout_user()
    flash('You have been logged out.', 'info')
    return redirect(url_for('auth.login'))


@auth_bp.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    if request.method == 'POST':
        current_user.full_name = request.form.get('full_name', current_user.full_name)
        current_user.phone = request.form.get('phone', current_user.phone)
        current_user.department = request.form.get('department', current_user.department)
        db.session.commit()
        flash('Profile updated.', 'success')
    return render_template('auth/profile.html')


@auth_bp.route('/two-factor', methods=['GET', 'POST'])
@login_required
def two_factor():
    if request.method == 'POST':
        token = request.form.get('token', '').strip()
        if current_user.verify_totp(token):
            flash('Two-factor authentication verified.', 'success')
        else:
            flash('Invalid token.', 'danger')

    qr_uri = None
    if current_user.two_factor_enabled and current_user.totp_secret:
        import pyotp
        totp = pyotp.TOTP(current_user.totp_secret)
        qr_uri = totp.provisioning_uri(name=current_user.email, issuer_name='EBB Airside Ops')

    return render_template('auth/two_factor.html', qr_uri=qr_uri)


@auth_bp.route('/two-factor/setup', methods=['POST'])
@login_required
def setup_two_factor():
    current_user.generate_totp_secret()
    current_user.two_factor_enabled = True
    db.session.commit()
    flash('Two-factor authentication enabled.', 'success')
    return redirect(url_for('auth.two_factor'))
