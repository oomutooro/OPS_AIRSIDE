"""
Permit models: ADP Applications, ADP Permits, AVP tracking.
"""
from datetime import datetime, date
from app import db


class ADPApplication(db.Model):
    """Form 17 - Airside Driving Permit Application."""
    __tablename__ = 'adp_applications'

    id = db.Column(db.Integer, primary_key=True)
    application_no = db.Column(db.String(32), unique=True, nullable=True)
    application_date = db.Column(db.Date, default=date.today, nullable=False)
    applicant_name = db.Column(db.String(128), nullable=False)
    applicant_badge = db.Column(db.String(32), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    job_title = db.Column(db.String(64), nullable=True)
    phone = db.Column(db.String(32), nullable=True)
    email = db.Column(db.String(120), nullable=True)

    # National Driving License
    national_driving_license_no = db.Column(db.String(32), nullable=True)
    ndl_expiry = db.Column(db.Date, nullable=True)
    ndl_categories = db.Column(db.JSON, default=list)  # A|B|C|D|E from national permit

    # ADP vehicle categories requested
    # brown=cars/vans/pickups/forklifts/tugs
    # green=fuel/pushback/highloaders/ambulift/catering/fire trucks
    # blue=ramp bus/coaster
    # red=apron equipment
    vehicle_categories_requested = db.Column(db.JSON, default=list)

    # Training
    training_completed_date = db.Column(db.Date, nullable=True)
    theory_test_score = db.Column(db.Float, nullable=True)
    practical_test_passed = db.Column(db.Boolean, nullable=True)
    training_notes = db.Column(db.Text, nullable=True)

    # Sponsor/Employer details
    sponsor_name = db.Column(db.String(128), nullable=True)
    sponsor_title = db.Column(db.String(64), nullable=True)
    sponsor_signature = db.Column(db.Text, nullable=True)
    sponsor_date = db.Column(db.Date, nullable=True)

    # Applicant declaration signature
    applicant_signature = db.Column(db.Text, nullable=True)

    # Processing
    status = db.Column(db.String(32), default='submitted')
    # submitted|under_review|approved|rejected|pending_training|pending_test
    approved_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    approval_date = db.Column(db.Date, nullable=True)
    rejection_reason = db.Column(db.Text, nullable=True)
    adp_number = db.Column(db.String(32), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = db.relationship('Company', backref='adp_applications')
    approved_by = db.relationship('User', foreign_keys=[approved_by_user_id])
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    PASS_MARK = 70.0  # 70% required for written test

    def is_eligible(self) -> bool:
        """Check if applicant meets eligibility requirements."""
        if self.theory_test_score is None:
            return False
        return (self.theory_test_score >= self.PASS_MARK and
                self.practical_test_passed is True and
                self.ndl_expiry and self.ndl_expiry >= date.today())

    def to_dict(self):
        return {
            'id': self.id,
            'application_no': self.application_no,
            'applicant_name': self.applicant_name,
            'company_id': self.company_id,
            'vehicle_categories_requested': self.vehicle_categories_requested,
            'theory_test_score': self.theory_test_score,
            'status': self.status,
            'application_date': self.application_date.isoformat() if self.application_date else None,
        }

    def __repr__(self):
        return f'<ADPApplication {self.application_no} - {self.applicant_name}>'


class ADPPermit(db.Model):
    """Issued Airside Driving Permits."""
    __tablename__ = 'adp_permits'

    id = db.Column(db.Integer, primary_key=True)
    adp_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    holder_name = db.Column(db.String(128), nullable=False)
    holder_badge = db.Column(db.String(32), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    application_id = db.Column(db.Integer, db.ForeignKey('adp_applications.id'), nullable=True)

    # ADP details
    colour_code = db.Column(db.String(8), nullable=False)  # brown|green|blue|red
    vehicle_categories = db.Column(db.JSON, default=list)
    issue_date = db.Column(db.Date, nullable=False)
    expiry_date = db.Column(db.Date, nullable=False)
    # ADP is valid for 2 years

    # Violation tracking (three strikes rule)
    violations_count = db.Column(db.Integer, default=0)
    punch_count = db.Column(db.Integer, default=0)  # 3 punches = suspension
    is_active = db.Column(db.Boolean, default=True)
    is_suspended = db.Column(db.Boolean, default=False)
    suspended_date = db.Column(db.Date, nullable=True)
    suspended_reason = db.Column(db.Text, nullable=True)
    suspended_until = db.Column(db.Date, nullable=True)

    # Refresher training
    refresher_due_date = db.Column(db.Date, nullable=True)
    refresher_completed_date = db.Column(db.Date, nullable=True)

    issued_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = db.relationship('Company', backref='adp_permits')
    application = db.relationship('ADPApplication', backref='adp_permit')
    issued_by = db.relationship('User', backref='issued_adp_permits')

    # ADP colour code definitions from manual
    COLOUR_DEFINITIONS = {
        'red': 'Apron equipment (GPU, ground power, etc.)',
        'green': 'Fuel dispensers, pushback tractors, highloaders, low loaders, ambulift, '
                 'pallet loaders, mobile pax steps, catering trucks, lorries, conveyor trucks, fire trucks',
        'blue': 'Ramp buses, coasters',
        'brown': 'Cars, vans, pick-ups, forklifts, towing tractors, electric tugs, station wagons',
    }

    ADP_VALIDITY_YEARS = 2

    @property
    def is_current(self) -> bool:
        return self.is_active and not self.is_suspended and self.expiry_date >= date.today()

    @property
    def days_to_expiry(self) -> int:
        return (self.expiry_date - date.today()).days

    def punch_adp(self, reason: str = '') -> bool:
        """Apply a punch to the ADP (three strikes rule)."""
        self.punch_count += 1
        self.violations_count += 1
        if self.punch_count >= 3:
            self.is_suspended = True
            self.suspended_date = date.today()
            self.suspended_reason = reason or 'Three strikes - ADP suspended'
        return self.is_suspended

    def to_dict(self):
        return {
            'id': self.id,
            'adp_number': self.adp_number,
            'holder_name': self.holder_name,
            'holder_badge': self.holder_badge,
            'colour_code': self.colour_code,
            'issue_date': self.issue_date.isoformat() if self.issue_date else None,
            'expiry_date': self.expiry_date.isoformat() if self.expiry_date else None,
            'is_current': self.is_current,
            'punch_count': self.punch_count,
            'is_suspended': self.is_suspended,
        }

    def __repr__(self):
        return f'<ADPPermit {self.adp_number} ({self.colour_code.upper()}) - {self.holder_name}>'
