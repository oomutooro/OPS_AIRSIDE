"""
Permit models: ADP Applications, ADP Permits, AVP tracking.
"""
from datetime import datetime, date
from sqlalchemy.orm import foreign
from app import db
from app.models.incident import Violation


UGANDA_ADP_DRIVER_CLASSES = {
    'A1': 'A1 - Light motorcycles',
    'A': 'A - Motorcycles',
    'B1': 'B1 - Light motor vehicles',
    'B': 'B - Motor vehicles (cars)',
    'BE': 'BE - Motor vehicles with trailer',
    'C1': 'C1 - Light goods vehicles',
    'C1E': 'C1E - C1 with trailer',
    'C': 'C - Medium goods vehicles',
    'CE': 'CE - C with trailer',
    'D1': 'D1 - Small passenger vehicles / minibuses',
    'D1E': 'D1E - D1 with trailer',
    'D': 'D - Buses and coaches',
    'DE': 'DE - D with trailer',
    'G': 'G - Agricultural / special purpose machinery',
}


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


class ADPProfile(db.Model):
    """ADP holder registry with company, training, licence, and violation history."""
    __tablename__ = 'adp_profiles'

    id = db.Column(db.Integer, primary_key=True)
    adp_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(128), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False)
    badge_number = db.Column(db.String(32), nullable=True)
    job_title = db.Column(db.String(64), nullable=True)
    date_of_birth = db.Column(db.Date, nullable=True)
    gender = db.Column(db.String(16), nullable=True)
    phone = db.Column(db.String(32), nullable=True)
    email = db.Column(db.String(120), nullable=True)

    adp_training_completed = db.Column(db.Boolean, default=False)
    adp_training_date = db.Column(db.Date, nullable=True)
    is_ucaa_staff = db.Column(db.Boolean, default=False)
    has_touch_key = db.Column(db.Boolean, default=False)
    touch_key_number = db.Column(db.String(32), nullable=True)

    national_driving_license_no = db.Column(db.String(32), nullable=True)
    ndl_expiry = db.Column(db.Date, nullable=True)
    driver_license_classes = db.Column(db.JSON, default=list)

    notes = db.Column(db.Text, nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = db.relationship('Company', backref='adp_profiles')
    created_by = db.relationship('User', backref='created_adp_profiles')
    violations = db.relationship(
        'Violation',
        primaryjoin=lambda: foreign(Violation.offender_adp_number) == ADPProfile.adp_number,
        viewonly=True,
        lazy='dynamic',
    )

    @property
    def company_details(self) -> str:
        if not self.company:
            return '-'
        parts = [self.company.name]
        if self.company.code:
            parts.append(self.company.code)
        if self.company.company_type:
            parts.append(self.company.company_type)
        return ' | '.join(parts)

    @property
    def training_status_label(self) -> str:
        return 'Completed' if self.adp_training_completed else 'Not completed'

    @property
    def touch_key_status_label(self) -> str:
        if not self.is_ucaa_staff:
            return 'Not UCAA'
        return 'Has touch key' if self.has_touch_key else 'No touch key'

    @property
    def driver_license_class_labels(self):
        classes = self.driver_license_classes or []
        return [UGANDA_ADP_DRIVER_CLASSES.get(code, code) for code in classes]

    @property
    def violation_count(self) -> int:
        return self.violations.count() if self.adp_number else 0

    @property
    def has_violations(self) -> bool:
        return self.violation_count > 0

    def to_dict(self):
        return {
            'id': self.id,
            'adp_number': self.adp_number,
            'full_name': self.full_name,
            'company_id': self.company_id,
            'company_details': self.company_details,
            'adp_training_completed': self.adp_training_completed,
            'adp_training_date': self.adp_training_date.isoformat() if self.adp_training_date else None,
            'is_ucaa_staff': self.is_ucaa_staff,
            'has_touch_key': self.has_touch_key,
            'national_driving_license_no': self.national_driving_license_no,
            'ndl_expiry': self.ndl_expiry.isoformat() if self.ndl_expiry else None,
            'driver_license_classes': self.driver_license_classes,
            'violation_count': self.violation_count,
        }

    def __repr__(self):
        return f'<ADPProfile {self.adp_number} - {self.full_name}>'
