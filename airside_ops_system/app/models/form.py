"""
Generic form template and submission models.
"""
from datetime import datetime
from app import db


class FormTemplate(db.Model):
    """Metadata for each of the 25 forms from the manual."""
    __tablename__ = 'form_templates'

    id = db.Column(db.Integer, primary_key=True)
    form_number = db.Column(db.Integer, unique=True, nullable=False, index=True)
    title = db.Column(db.String(256), nullable=False)
    description = db.Column(db.Text, nullable=True)
    version = db.Column(db.String(16), default='1.0')
    category = db.Column(db.String(64), nullable=True)
    # Category: inspection|safety|permit|apron|report|audit
    route_endpoint = db.Column(db.String(128), nullable=True)
    schema_definition = db.Column(db.JSON, default=dict)
    ui_layout = db.Column(db.JSON, default=dict)
    is_active = db.Column(db.Boolean, default=True)
    requires_signature = db.Column(db.Boolean, default=True)
    requires_approval = db.Column(db.Boolean, default=False)
    allowed_roles = db.Column(db.JSON, default=list)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    submissions = db.relationship('FormSubmission', backref='template', lazy='dynamic')

    def __repr__(self):
        return f'<FormTemplate Form-{self.form_number}: {self.title}>'


class FormSubmission(db.Model):
    """A submitted or drafted instance of any form."""
    __tablename__ = 'form_submissions'

    id = db.Column(db.Integer, primary_key=True)
    form_template_id = db.Column(db.Integer, db.ForeignKey('form_templates.id'), nullable=False)
    reference_number = db.Column(db.String(32), unique=True, nullable=True, index=True)
    submission_date = db.Column(db.Date, nullable=True)
    submission_time = db.Column(db.Time, nullable=True)
    status = db.Column(db.String(32), default='draft', nullable=False)
    # Status: draft|submitted|approved|rejected|closed
    submitted_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approval_date = db.Column(db.DateTime, nullable=True)
    approval_notes = db.Column(db.Text, nullable=True)
    location_ref = db.Column(db.String(128), nullable=True)
    shift = db.Column(db.String(16), nullable=True)  # day|night
    weather_conditions = db.Column(db.JSON, default=dict)
    gps_latitude = db.Column(db.Float, nullable=True)
    gps_longitude = db.Column(db.Float, nullable=True)
    data = db.Column(db.JSON, default=dict, nullable=False)
    # All form-specific field data stored here
    outgoing_signature = db.Column(db.Text, nullable=True)  # base64 signature image
    incoming_signature = db.Column(db.Text, nullable=True)
    supervisor_signature = db.Column(db.Text, nullable=True)
    is_draft_saved = db.Column(db.Boolean, default=False)
    draft_data = db.Column(db.JSON, default=dict)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    approver = db.relationship('User', foreign_keys=[approved_by_user_id], backref='approved_forms')
    attachments = db.relationship('Attachment', backref='submission', lazy='dynamic',
                                   cascade='all, delete-orphan')

    def generate_reference_number(self, prefix='FORM'):
        """Generate a unique reference number."""
        from datetime import date
        date_str = date.today().strftime('%Y%m%d')
        self.reference_number = f"{prefix}-{date_str}-{self.id:05d}"
        return self.reference_number

    def to_dict(self):
        return {
            'id': self.id,
            'form_template_id': self.form_template_id,
            'reference_number': self.reference_number,
            'submission_date': self.submission_date.isoformat() if self.submission_date else None,
            'status': self.status,
            'submitted_by_user_id': self.submitted_by_user_id,
            'location_ref': self.location_ref,
            'data': self.data,
            'created_at': self.created_at.isoformat(),
        }

    def __repr__(self):
        return f'<FormSubmission #{self.id} Form-{self.form_template_id} [{self.status}]>'


class Attachment(db.Model):
    """File attachments linked to form submissions."""
    __tablename__ = 'attachments'

    id = db.Column(db.Integer, primary_key=True)
    submission_id = db.Column(db.Integer, db.ForeignKey('form_submissions.id'), nullable=True)
    form_template_id = db.Column(db.Integer, nullable=True)
    field_name = db.Column(db.String(128), nullable=True)
    original_filename = db.Column(db.String(256), nullable=False)
    stored_filename = db.Column(db.String(256), nullable=False)
    file_path = db.Column(db.String(512), nullable=False)
    file_type = db.Column(db.String(32), nullable=True)
    file_size_bytes = db.Column(db.Integer, nullable=True)
    description = db.Column(db.String(256), nullable=True)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    uploaded_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    uploader = db.relationship('User', backref='uploads')

    def __repr__(self):
        return f'<Attachment {self.original_filename}>'


class AuditLog(db.Model):
    """Immutable audit trail for all system actions (INSERT ONLY - no updates/deletes)."""
    __tablename__ = 'audit_log'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    action = db.Column(db.String(64), nullable=False)
    # e.g. SUBMIT_FORM, APPROVE_FORM, CREATE_VIOLATION, LOGIN, etc.
    entity_type = db.Column(db.String(64), nullable=True)
    entity_id = db.Column(db.Integer, nullable=True)
    form_template_id = db.Column(db.Integer, nullable=True)
    submission_id = db.Column(db.Integer, nullable=True)
    old_data = db.Column(db.JSON, nullable=True)
    new_data = db.Column(db.JSON, nullable=True)
    ip_address = db.Column(db.String(45), nullable=True)
    user_agent = db.Column(db.String(256), nullable=True)
    description = db.Column(db.Text, nullable=True)
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False, index=True)

    user = db.relationship('User', backref='audit_logs')

    @classmethod
    def log(cls, action, user_id=None, entity_type=None, entity_id=None,
            old_data=None, new_data=None, ip_address=None, description=None,
            form_template_id=None, submission_id=None, user_agent=None):
        """Create a new audit log entry. Thread-safe INSERT only."""
        from flask import request as flask_request
        from app import db
        if ip_address is None:
            try:
                ip_address = flask_request.remote_addr
            except RuntimeError:
                ip_address = None
        if user_agent is None:
            try:
                user_agent = flask_request.headers.get('User-Agent', '')[:256]
            except RuntimeError:
                user_agent = None

        entry = cls(
            user_id=user_id,
            action=action,
            entity_type=entity_type,
            entity_id=entity_id,
            form_template_id=form_template_id,
            submission_id=submission_id,
            old_data=old_data,
            new_data=new_data,
            ip_address=ip_address,
            user_agent=user_agent,
            description=description,
        )
        db.session.add(entry)
        # Note: caller must commit the session
        return entry

    def __repr__(self):
        return f'<AuditLog {self.action} by User#{self.user_id} at {self.timestamp}>'
