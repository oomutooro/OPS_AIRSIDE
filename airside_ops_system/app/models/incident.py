"""
Incident and Violation models (Forms 10, 11, 15, 16).
"""
from datetime import datetime
from app import db


class ViolationType(db.Model):
    """Violation types with standard penalties from Attachment 1 of the manual."""
    __tablename__ = 'violation_types'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), unique=True, nullable=False)
    description = db.Column(db.String(256), nullable=False)
    standard_penalty_ugx = db.Column(db.Float, nullable=True)
    standard_penalty_usd = db.Column(db.Float, nullable=True)
    penalty_currency = db.Column(db.String(4), default='UGX')  # UGX|USD
    is_per_unit = db.Column(db.Boolean, default=False, doc='Penalty multiplied per m² or per item')
    unit_description = db.Column(db.String(64), nullable=True)  # e.g. 'per square meter'
    severity = db.Column(db.String(16), default='moderate')  # minor|moderate|serious|critical
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    violations = db.relationship('Violation', backref='violation_type_ref', lazy='dynamic')

    def __repr__(self):
        return f'<ViolationType {self.code}: {self.description}>'


class Violation(db.Model):
    """Form 15 & 16 - Airside Violation and On-Spot Report."""
    __tablename__ = 'violations'

    id = db.Column(db.Integer, primary_key=True)
    violation_number = db.Column(db.String(32), unique=True, nullable=True, index=True)
    form_type = db.Column(db.String(16), default='form_15')  # form_15|form_16 (spot check)

    # Offender details
    offender_name = db.Column(db.String(128), nullable=True)
    offender_badge = db.Column(db.String(32), nullable=True)
    offender_company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    offender_adp_number = db.Column(db.String(32), nullable=True)
    vehicle_registration = db.Column(db.String(32), nullable=True)
    vehicle_type = db.Column(db.String(64), nullable=True)

    # Violation details
    violation_type_id = db.Column(db.Integer, db.ForeignKey('violation_types.id'), nullable=True)
    violation_description = db.Column(db.Text, nullable=False)
    violation_location = db.Column(db.String(128), nullable=True)
    violation_date = db.Column(db.Date, nullable=False)
    violation_time = db.Column(db.Time, nullable=True)
    speed_recorded_kmh = db.Column(db.Float, nullable=True)  # For over-speeding violations

    # Penalty
    penalty_amount = db.Column(db.Float, nullable=True)
    penalty_currency = db.Column(db.String(4), default='UGX')
    unit_quantity = db.Column(db.Float, nullable=True, doc='For per-unit penalties (e.g., m²)')

    # Status and follow-up
    status = db.Column(db.String(32), default='open')
    # open|acknowledged|payment_pending|paid|appealed|cancelled|adp_punched
    payment_receipt_no = db.Column(db.String(32), nullable=True)
    payment_date = db.Column(db.Date, nullable=True)
    adp_punched = db.Column(db.Boolean, default=False)
    adp_permit_id = db.Column(db.Integer, db.ForeignKey('adp_permits.id'), nullable=True)

    # Offender acknowledgement
    offender_acknowledgement = db.Column(db.Text, nullable=True)
    offender_signature = db.Column(db.Text, nullable=True)  # base64 signature
    offender_acknowledgement_date = db.Column(db.DateTime, nullable=True)

    # Employer/company commitment
    employer_name = db.Column(db.String(128), nullable=True)
    employer_title = db.Column(db.String(64), nullable=True)
    employer_signature = db.Column(db.Text, nullable=True)
    employer_commitment_date = db.Column(db.Date, nullable=True)

    # Issuing officer details
    issuing_officer_name = db.Column(db.String(128), nullable=True)
    issuing_officer_badge = db.Column(db.String(32), nullable=True)
    issuing_officer_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    issuing_officer_signature = db.Column(db.Text, nullable=True)

    # Witness
    witness_name = db.Column(db.String(128), nullable=True)
    witness_badge = db.Column(db.String(32), nullable=True)

    photo_path = db.Column(db.String(256), nullable=True)
    gps_latitude = db.Column(db.Float, nullable=True)
    gps_longitude = db.Column(db.Float, nullable=True)
    notes = db.Column(db.Text, nullable=True)

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    offender_company = db.relationship('Company', backref='violations')
    issuing_officer = db.relationship('User', backref='issued_violations')
    adp_permit = db.relationship('ADPPermit', backref='violations')

    def calculate_penalty(self) -> float:
        """Calculate total penalty based on type and quantity."""
        if not self.violation_type_ref:
            return self.penalty_amount or 0
        base = self.violation_type_ref.standard_penalty_ugx or 0
        if self.violation_type_ref.is_per_unit and self.unit_quantity:
            return base * self.unit_quantity
        return base

    def to_dict(self):
        return {
            'id': self.id,
            'violation_number': self.violation_number,
            'offender_name': self.offender_name,
            'offender_badge': self.offender_badge,
            'vehicle_registration': self.vehicle_registration,
            'violation_description': self.violation_description,
            'violation_location': self.violation_location,
            'violation_date': self.violation_date.isoformat() if self.violation_date else None,
            'penalty_amount': self.penalty_amount,
            'penalty_currency': self.penalty_currency,
            'status': self.status,
        }

    def __repr__(self):
        return f'<Violation {self.violation_number} [{self.status}]>'


class Incident(db.Model):
    """Forms 10 & 11 - Incident/Accident Report and Preliminary Investigation."""
    __tablename__ = 'incidents'

    id = db.Column(db.Integer, primary_key=True)
    incident_number = db.Column(db.String(32), unique=True, nullable=True, index=True)
    report_type = db.Column(db.String(32), default='report')  # report (Form 10)|investigation (Form 11)

    # Occurrence details
    report_date = db.Column(db.Date, nullable=False)
    occurrence_date = db.Column(db.Date, nullable=False)
    occurrence_time = db.Column(db.Time, nullable=True)
    location = db.Column(db.String(128), nullable=True)
    gps_latitude = db.Column(db.Float, nullable=True)
    gps_longitude = db.Column(db.Float, nullable=True)

    incident_type = db.Column(db.String(32), nullable=False)
    # accident|incident|near_miss|runway_incursion|bird_strike|wildlife
    severity = db.Column(db.String(16), default='minor')  # minor|moderate|major|critical

    # Narrative
    description = db.Column(db.Text, nullable=False)
    sequence_of_events = db.Column(db.Text, nullable=True)
    immediate_actions_taken = db.Column(db.Text, nullable=True)

    # Involved parties
    aircraft_registration = db.Column(db.String(16), nullable=True)
    aircraft_type = db.Column(db.String(32), nullable=True)
    airline_operator = db.Column(db.String(128), nullable=True)
    flight_number = db.Column(db.String(16), nullable=True)
    vehicle_registration = db.Column(db.String(32), nullable=True)
    vehicle_operator_name = db.Column(db.String(128), nullable=True)

    # Injuries/damage
    injuries = db.Column(db.JSON, default=list)  # list of {person, nature, severity}
    fatalities = db.Column(db.Integer, default=0)
    aircraft_damage = db.Column(db.Text, nullable=True)
    vehicle_damage = db.Column(db.Text, nullable=True)
    infrastructure_damage = db.Column(db.Text, nullable=True)

    # Reporting chain (time-based SLA)
    reported_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    reported_at = db.Column(db.DateTime, nullable=True)
    # Operator must report within 4 hours
    operator_report_deadline = db.Column(db.DateTime, nullable=True)
    operator_report_submitted = db.Column(db.Boolean, default=False)

    # OO/AS final report within 8 hours
    oo_report_deadline = db.Column(db.DateTime, nullable=True)
    oo_report_submitted = db.Column(db.Boolean, default=False)
    oo_report_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # SOO/AS/SC submits to POO and MO within 12 hours
    soo_report_deadline = db.Column(db.DateTime, nullable=True)
    soo_report_submitted = db.Column(db.Boolean, default=False)
    soo_report_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # Investigation (Form 11)
    investigator_name = db.Column(db.String(128), nullable=True)
    investigator_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    investigation_date = db.Column(db.Date, nullable=True)
    investigation_findings = db.Column(db.Text, nullable=True)
    probable_cause = db.Column(db.Text, nullable=True)
    contributing_factors = db.Column(db.JSON, default=list)
    recommendations = db.Column(db.JSON, default=list)  # list of {action, responsible, deadline}
    corrective_actions = db.Column(db.JSON, default=list)

    status = db.Column(db.String(32), default='open')
    # open|under_investigation|under_review|closed|cancelled
    closed_date = db.Column(db.Date, nullable=True)
    arff_notified = db.Column(db.Boolean, default=False)
    media_involved = db.Column(db.Boolean, default=False)

    weather_conditions = db.Column(db.JSON, default=dict)
    photos = db.Column(db.JSON, default=list)  # list of file paths

    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    reported_by = db.relationship('User', foreign_keys=[reported_by_user_id])
    investigator = db.relationship('User', foreign_keys=[investigator_user_id])

    def set_reporting_deadlines(self):
        """Set all SLA deadlines based on occurrence time."""
        from datetime import timedelta
        if self.reported_at:
            self.operator_report_deadline = self.reported_at + timedelta(hours=4)
            self.oo_report_deadline = self.reported_at + timedelta(hours=8)
            self.soo_report_deadline = self.reported_at + timedelta(hours=12)

    def to_dict(self):
        return {
            'id': self.id,
            'incident_number': self.incident_number,
            'incident_type': self.incident_type,
            'severity': self.severity,
            'occurrence_date': self.occurrence_date.isoformat() if self.occurrence_date else None,
            'location': self.location,
            'status': self.status,
            'reported_by_user_id': self.reported_by_user_id,
        }

    def __repr__(self):
        return f'<Incident {self.incident_number} [{self.severity}] [{self.status}]>'
