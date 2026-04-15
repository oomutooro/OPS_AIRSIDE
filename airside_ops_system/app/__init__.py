"""
Flask application factory.
Entebbe International Airport - Airside Operations Management System
"""
import os
from flask import Flask, render_template, request, jsonify
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager
from flask_wtf.csrf import CSRFProtect
from flask_migrate import Migrate
from flask_bcrypt import Bcrypt
from flask_caching import Cache
from flask_mail import Mail
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_socketio import SocketIO

# Extension instances
db = SQLAlchemy()
login_manager = LoginManager()
csrf = CSRFProtect()
migrate = Migrate()
bcrypt = Bcrypt()
cache = Cache()
mail = Mail()
limiter = Limiter(key_func=get_remote_address)
socketio = SocketIO()


def create_app(config_name='default'):
    """Application factory pattern."""
    app = Flask(__name__, template_folder='templates', static_folder='static')

    # Load configuration
    from app.config import config
    app.config.from_object(config[config_name])
    _validate_aodb_config(app)

    # Initialize extensions
    db.init_app(app)
    login_manager.init_app(app)
    csrf.init_app(app)
    migrate.init_app(app, db)
    bcrypt.init_app(app)
    cache.init_app(app)
    mail.init_app(app)
    limiter.init_app(app)
    socketio.init_app(app, cors_allowed_origins="*", async_mode='threading')

    # Login manager configuration
    login_manager.login_view = 'auth.login'
    login_manager.login_message = 'Please log in to access the Airside Operations System.'
    login_manager.login_message_category = 'warning'
    login_manager.session_protection = 'strong'

    # Ensure upload directories exist
    _create_upload_dirs(app)

    # Register blueprints
    _register_blueprints(app)

    # Register error handlers
    _register_error_handlers(app)

    # Register template filters
    _register_template_filters(app)

    # Register context processors
    _register_context_processors(app)

    # Create tables if needed
    with app.app_context():
        db.create_all()

    # Start background scheduler (skip in test mode and reloader parent process)
    if not app.config.get('TESTING'):
        _start_aodb_scheduler(app)

    return app


def _validate_aodb_config(app):
    """Validate AODB auth settings to fail fast on invalid live configuration."""
    if app.config.get('TESTING'):
        return

    mock_mode = bool(app.config.get('AODB_MOCK_MODE', False))
    auth_key = (app.config.get('AODB_AUTH_KEY', '') or '').strip()
    user_id = (app.config.get('AODB_USER_ID', '') or '').strip()
    password = (app.config.get('AODB_PASSWORD', '') or '').strip()

    if mock_mode:
        return

    if not auth_key and not (user_id and password):
        raise RuntimeError(
            'AODB live mode requires authentication. Set AODB_AUTH_KEY '
            'or provide AODB_USER_ID and AODB_PASSWORD, or enable AODB_MOCK_MODE=True.'
        )

    if auth_key and (user_id or password):
        app.logger.info('AODB auth key detected; username/password fallback values will be ignored.')


def _start_aodb_scheduler(app):
    """Start APScheduler background jobs for AODB syncing (read and write-back)."""
    import os
    # In debug/reloader mode only start in the worker process, not the watcher parent
    if app.debug and os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        return
    try:
        from apscheduler.schedulers.background import BackgroundScheduler
        from apscheduler.triggers.interval import IntervalTrigger
        from app.services.aodb_sync import AodbSyncService
        from app.services.aodb_writeback import AodbWritebackService

        sync_interval_minutes = app.config.get('AODB_SYNC_INTERVAL_MINUTES', 15)
        writeback_interval_minutes = app.config.get('AODB_WRITEBACK_INTERVAL_MINUTES', 5)

        def _sync_job():
            with app.app_context():
                AodbSyncService.scheduled_sync()

        def _writeback_job():
            with app.app_context():
                AodbWritebackService.process_queue()

        scheduler = BackgroundScheduler(daemon=True)
        
        # Flight sync job
        scheduler.add_job(
            _sync_job,
            trigger=IntervalTrigger(minutes=sync_interval_minutes),
            id='aodb_flight_sync',
            name='AODB Flight Sync',
            replace_existing=True,
        )
        
        # Write-back processing job (more frequent — default 5 min)
        scheduler.add_job(
            _writeback_job,
            trigger=IntervalTrigger(minutes=writeback_interval_minutes),
            id='aodb_writeback_process',
            name='AODB Write-back Processor',
            replace_existing=True,
        )
        
        scheduler.start()
        app.logger.info(
            'AODB scheduler started: sync every %d min, write-back every %d min',
            sync_interval_minutes, writeback_interval_minutes,
        )
    except Exception as exc:
        app.logger.warning('Could not start AODB scheduler: %s', exc)


def _create_upload_dirs(app):
    """Create required upload directories."""
    upload_base = app.config.get('UPLOAD_FOLDER', 'app/static/uploads')
    for subdir in ['photos', 'signatures', 'documents']:
        path = os.path.join(upload_base, subdir)
        os.makedirs(path, exist_ok=True)


def _register_blueprints(app):
    """Register all application blueprints."""
    from app.routes.auth import auth_bp
    from app.routes.dashboard import dashboard_bp
    from app.routes.apron import apron_bp
    from app.routes.inspection import inspection_bp
    from app.routes.safety import safety_bp
    from app.routes.permit import permit_bp
    from app.routes.report import report_bp
    from app.routes.admin import admin_bp

    app.register_blueprint(auth_bp, url_prefix='/auth')
    app.register_blueprint(dashboard_bp, url_prefix='/')
    app.register_blueprint(apron_bp, url_prefix='/apron')
    app.register_blueprint(inspection_bp, url_prefix='/inspection')
    app.register_blueprint(safety_bp, url_prefix='/safety')
    app.register_blueprint(permit_bp, url_prefix='/permit')
    app.register_blueprint(report_bp, url_prefix='/report')
    app.register_blueprint(admin_bp, url_prefix='/admin')


def _register_error_handlers(app):
    """Register custom error handlers."""

    @app.errorhandler(400)
    def bad_request(e):
        if request.is_json:
            return jsonify(error='Bad Request', message=str(e)), 400
        return render_template('errors/400.html', error=e), 400

    @app.errorhandler(403)
    def forbidden(e):
        if request.is_json:
            return jsonify(error='Forbidden', message='Access denied.'), 403
        return render_template('errors/403.html', error=e), 403

    @app.errorhandler(404)
    def not_found(e):
        if request.is_json:
            return jsonify(error='Not Found', message=str(e)), 404
        return render_template('errors/404.html', error=e), 404

    @app.errorhandler(429)
    def rate_limit_exceeded(e):
        if request.is_json:
            return jsonify(error='Too Many Requests', message='Rate limit exceeded.'), 429
        return render_template('errors/429.html', error=e), 429

    @app.errorhandler(500)
    def internal_error(e):
        db.session.rollback()
        if request.is_json:
            return jsonify(error='Internal Server Error'), 500
        return render_template('errors/500.html', error=e), 500


def _register_template_filters(app):
    """Register Jinja2 template filters."""
    from datetime import datetime

    @app.template_filter('datetime_fmt')
    def datetime_fmt(value, fmt='%d %b %Y %H:%M'):
        if value is None:
            return '-'
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError:
                return value
        return value.strftime(fmt)

    @app.template_filter('date_fmt')
    def date_fmt(value, fmt='%d %b %Y'):
        if value is None:
            return '-'
        if isinstance(value, str):
            try:
                from datetime import date
                value = date.fromisoformat(value)
            except ValueError:
                return value
        return value.strftime(fmt)

    @app.template_filter('currency_ugx')
    def currency_ugx(value):
        if value is None:
            return '-'
        try:
            return f"UGX {float(value):,.0f}"
        except (ValueError, TypeError):
            return str(value)

    @app.template_filter('status_badge')
    def status_badge(value):
        badges = {
            'draft': 'secondary',
            'submitted': 'primary',
            'approved': 'success',
            'rejected': 'danger',
            'pending': 'warning',
            'active': 'success',
            'expired': 'danger',
            'suspended': 'danger',
            'closed': 'dark',
            'open': 'warning',
            'in_progress': 'info',
        }
        color = badges.get(str(value).lower(), 'secondary')
        return f'<span class="badge bg-{color}">{str(value).replace("_", " ").title()}</span>'

    @app.template_filter('adp_badge')
    def adp_badge(value):
        colors = {
            'red': 'danger',
            'green': 'success',
            'blue': 'primary',
            'brown': 'warning',
        }
        color = colors.get(str(value).lower(), 'secondary')
        label = str(value).upper()
        return f'<span class="badge bg-{color}">{label}</span>'


def _register_context_processors(app):
    """Register template context processors."""

    @app.context_processor
    def inject_globals():
        from flask_login import current_user
        from datetime import datetime
        unread_count = 0
        if current_user.is_authenticated:
            # Count unread notifications (placeholder)
            pass
        return {
            'app_name': app.config.get('APP_NAME', 'Airside Ops'),
            'app_version': app.config.get('APP_VERSION', '1.0.0'),
            'airport_icao': app.config.get('AIRPORT_ICAO', 'HUEN'),
            'now': datetime.utcnow(),
            'unread_notifications': unread_count,
        }
