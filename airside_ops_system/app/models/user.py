"""
User and Role models for authentication and authorization.
"""
from datetime import datetime
from flask_login import UserMixin
from app import db, bcrypt, login_manager


class User(UserMixin, db.Model):
    """Application user with role-based access control."""
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(64), unique=True, nullable=False, index=True)
    password_hash = db.Column(db.String(256), nullable=False)
    role = db.Column(db.String(32), nullable=False, default='viewer')
    # Roles: admin | supervisor | inspector | operator | auditor | viewer
    full_name = db.Column(db.String(128), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False, index=True)
    badge_number = db.Column(db.String(32), unique=True, nullable=True)
    department = db.Column(db.String(128), nullable=True)
    phone = db.Column(db.String(32), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True, nullable=False)
    two_factor_enabled = db.Column(db.Boolean, default=False)
    totp_secret = db.Column(db.String(64), nullable=True)
    last_login = db.Column(db.DateTime, nullable=True)
    password_changed_at = db.Column(db.DateTime, default=datetime.utcnow)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = db.relationship('Company', backref='users', foreign_keys=[company_id])
    form_submissions = db.relationship('FormSubmission', backref='submitted_by',
                                       foreign_keys='FormSubmission.submitted_by_user_id', lazy='dynamic')

    # Role permission sets
    ROLE_PERMISSIONS = {
        'admin': {'all'},
        'supervisor': {
            'view_dashboard', 'manage_forms', 'approve_forms', 'view_reports',
            'manage_shifts', 'manage_violations', 'view_analytics', 'export_data',
            'manage_incidents', 'manage_adp', 'manage_vehicles',
        },
        'inspector': {
            'view_dashboard', 'submit_forms', 'view_own_forms', 'create_incidents',
            'create_violations', 'view_reports',
        },
        'operator': {
            'view_dashboard', 'submit_forms', 'view_own_forms',
        },
        'auditor': {
            'view_dashboard', 'view_all_forms', 'view_reports', 'view_analytics',
            'export_data',
        },
        'viewer': {
            'view_dashboard', 'view_own_forms',
        },
    }

    def set_password(self, password: str) -> None:
        """Hash and store the password."""
        self.password_hash = bcrypt.generate_password_hash(
            password, rounds=12
        ).decode('utf-8')
        self.password_changed_at = datetime.utcnow()

    def check_password(self, password: str) -> bool:
        """Verify a plaintext password against the stored hash."""
        return bcrypt.check_password_hash(self.password_hash, password)

    def has_permission(self, permission: str) -> bool:
        """Check if user has a specific permission."""
        perms = self.ROLE_PERMISSIONS.get(self.role, set())
        return 'all' in perms or permission in perms

    def can(self, *permissions) -> bool:
        """Check if user has all specified permissions."""
        return all(self.has_permission(p) for p in permissions)

    @property
    def is_admin(self) -> bool:
        return self.role == 'admin'

    @property
    def is_supervisor(self) -> bool:
        return self.role in ('admin', 'supervisor')

    def record_login(self):
        """Update last login timestamp."""
        self.last_login = datetime.utcnow()
        db.session.commit()

    def generate_totp_secret(self):
        """Generate a new TOTP secret for 2FA."""
        import pyotp
        self.totp_secret = pyotp.random_base32()
        return self.totp_secret

    def verify_totp(self, token: str) -> bool:
        """Verify a TOTP token."""
        if not self.totp_secret:
            return False
        import pyotp
        totp = pyotp.TOTP(self.totp_secret)
        return totp.verify(token, valid_window=1)

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'username': self.username,
            'full_name': self.full_name,
            'email': self.email,
            'role': self.role,
            'badge_number': self.badge_number,
            'department': self.department,
            'is_active': self.is_active,
            'last_login': self.last_login.isoformat() if self.last_login else None,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<User {self.username} ({self.role})>'


class Role(db.Model):
    """Custom role definitions with JSON permissions (extensible)."""
    __tablename__ = 'roles'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(64), unique=True, nullable=False)
    description = db.Column(db.String(256))
    permissions = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Role {self.name}>'


@login_manager.user_loader
def load_user(user_id: str):
    """Load user by ID for Flask-Login."""
    return db.session.get(User, int(user_id))


class Notification(db.Model):
    """In-app notification for users."""
    __tablename__ = 'notifications'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    title = db.Column(db.String(128), nullable=False)
    message = db.Column(db.Text, nullable=False)
    notification_type = db.Column(db.String(32), default='info')  # info|warning|danger|success
    link_url = db.Column(db.String(256), nullable=True)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    user = db.relationship('User', backref='notifications')

    def __repr__(self):
        return f'<Notification {self.title} -> User {self.user_id}>'
