"""
Inspection models: ESSAT (motorised & non-motorised), FOD cleaning, FOD walks, scheduled inspections.
"""
from datetime import datetime, date
from app import db


class ESSTATMotorisedInspection(db.Model):
    """Form 18 - ESSAT Checklist for motorised vehicles/equipment."""
    __tablename__ = 'esstat_motorised'

    id = db.Column(db.Integer, primary_key=True)
    reference_no = db.Column(db.String(32), unique=True, nullable=True)
    inspection_date = db.Column(db.Date, nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    vehicle_no = db.Column(db.String(32), nullable=False)
    colour = db.Column(db.String(32), nullable=True)
    vehicle_type = db.Column(db.String(64), nullable=True)
    manufacture_date = db.Column(db.String(16), nullable=True)
    sticker_no = db.Column(db.String(32), nullable=True)
    sticker_expiry = db.Column(db.Date, nullable=True)

    # ESSAT team members (JSON list of {name, role})
    essat_members = db.Column(db.JSON, default=list)

    # Full inspection checklist data (JSON)
    # Sections: EMV, Electrical System, Leakages, Safety Equipment,
    #           Braking Systems, Ground Handling Equipment, ARFFS, EJAF
    checklist = db.Column(db.JSON, default=dict)

    remarks = db.Column(db.Text, nullable=True)
    recommendations = db.Column(db.Text, nullable=True)
    defects_found = db.Column(db.Boolean, default=False)
    outcome = db.Column(db.String(16), default='pending')  # pass|fail|conditional|pending

    # Signatures
    secretary_name = db.Column(db.String(128), nullable=True)
    secretary_sign = db.Column(db.Text, nullable=True)
    chairperson_name = db.Column(db.String(128), nullable=True)
    chairperson_sign = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(32), default='draft')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = db.relationship('Company', backref='esstat_inspections')
    creator = db.relationship('User', backref='esstat_motorised_created')

    def to_dict(self):
        return {
            'id': self.id,
            'reference_no': self.reference_no,
            'inspection_date': self.inspection_date.isoformat() if self.inspection_date else None,
            'vehicle_no': self.vehicle_no,
            'vehicle_type': self.vehicle_type,
            'outcome': self.outcome,
            'status': self.status,
        }

    def __repr__(self):
        return f'<ESSTATMotorisedInspection {self.vehicle_no} {self.inspection_date}>'


class ESSTATNonMotorisedInspection(db.Model):
    """Form 19 - Dolly/Cart Audit Form (non-motorised equipment)."""
    __tablename__ = 'esstat_non_motorised'

    id = db.Column(db.Integer, primary_key=True)
    reference_no = db.Column(db.String(32), unique=True, nullable=True)
    inspection_date = db.Column(db.Date, nullable=False, index=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    dolly_no = db.Column(db.String(32), nullable=False)
    colour = db.Column(db.String(32), nullable=True)
    description = db.Column(db.String(128), nullable=True)  # baggage cart, dolly, etc.

    # Checklist: brakes, tyres, side reflectors, towbar
    checklist = db.Column(db.JSON, default=dict)
    defects = db.Column(db.Text, nullable=True)
    rectification_status = db.Column(db.String(32), nullable=True)  # pending|rectified|N/A

    # Inspectors (JSON list of {name, signature})
    inspectors = db.Column(db.JSON, default=list)
    secretary_name = db.Column(db.String(128), nullable=True)
    secretary_sign = db.Column(db.Text, nullable=True)
    outcome = db.Column(db.String(16), default='pending')  # pass|fail|conditional|pending

    status = db.Column(db.String(32), default='draft')
    created_by = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    company = db.relationship('Company', backref='dolly_inspections')

    def __repr__(self):
        return f'<ESSTATNonMotorisedInspection {self.dolly_no}>'


class FODCleaningRecord(db.Model):
    """Form 20 - FOD Cleaning Record."""
    __tablename__ = 'fod_cleaning_records'

    id = db.Column(db.Integer, primary_key=True)
    reference_no = db.Column(db.String(32), unique=True, nullable=True)
    cleaning_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    shift = db.Column(db.String(16), nullable=True)  # day|night

    # Areas cleaned (JSON list of area names)
    areas_cleaned = db.Column(db.JSON, default=list)
    # e.g. ["Apron 1", "Taxiway A1", "Runway 17/35 threshold"]

    cleaning_method = db.Column(db.String(32), nullable=True)
    # FOD BOSS|sweeping|scrubbing|walk|vacuum|pick during inspection

    # FOD types and quantities (JSON list of {type, quantity, unit})
    fod_types = db.Column(db.JSON, default=list)
    total_weight_kg = db.Column(db.Float, nullable=True)
    weather_conditions = db.Column(db.String(64), nullable=True)

    performed_by = db.Column(db.String(128), nullable=True)
    performed_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    supervised_by = db.Column(db.String(128), nullable=True)
    supervised_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    remarks = db.Column(db.Text, nullable=True)

    status = db.Column(db.String(32), default='submitted')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    performer = db.relationship('User', foreign_keys=[performed_by_user_id])
    supervisor = db.relationship('User', foreign_keys=[supervised_by_user_id])

    def __repr__(self):
        return f'<FODCleaningRecord {self.cleaning_date} {self.cleaning_method}>'


class FODWalk(db.Model):
    """Form 21 - Quarterly FOD Walk Report."""
    __tablename__ = 'fod_walks'

    id = db.Column(db.Integer, primary_key=True)
    reference_no = db.Column(db.String(32), unique=True, nullable=True)
    walk_date = db.Column(db.Date, nullable=False, index=True)
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)
    quarter = db.Column(db.String(8), nullable=True)  # Q1|Q2|Q3|Q4
    year = db.Column(db.Integer, nullable=True)

    # Participants (JSON list of {name, company, badge_no, signature})
    participants = db.Column(db.JSON, default=list)
    areas_covered = db.Column(db.JSON, default=list)

    # FOD collected (JSON list of {type, quantity, weight_kg})
    fod_collected = db.Column(db.JSON, default=list)
    total_weight_kg = db.Column(db.Float, nullable=True)

    organized_by = db.Column(db.String(128), nullable=True)
    organized_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    weather_conditions = db.Column(db.String(64), nullable=True)
    remarks = db.Column(db.Text, nullable=True)
    report_submitted = db.Column(db.Boolean, default=False)
    report_submitted_to = db.Column(db.String(128), nullable=True)

    status = db.Column(db.String(32), default='draft')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    organizer = db.relationship('User', foreign_keys=[organized_by_user_id])

    def __repr__(self):
        return f'<FODWalk {self.walk_date} Q{self.quarter}/{self.year}>'


class ScheduledInspection(db.Model):
    """Schedule tracker for recurring inspections."""
    __tablename__ = 'scheduled_inspections'

    id = db.Column(db.Integer, primary_key=True)
    inspection_type = db.Column(db.String(64), nullable=False)
    # ESSAT|runway|apron|fueling|FOD walk|manoeuvring area
    frequency = db.Column(db.String(32), nullable=False)
    # daily|weekly|monthly|quarterly|annual|shift_start|after_event
    last_performed = db.Column(db.DateTime, nullable=True)
    next_due = db.Column(db.DateTime, nullable=True, index=True)
    assigned_to_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    location = db.Column(db.String(128), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_overdue = db.Column(db.Boolean, default=False)
    related_form_number = db.Column(db.Integer, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    assigned_to = db.relationship('User', backref='assigned_inspections')

    def check_overdue(self):
        """Check and update overdue status."""
        if self.next_due and self.next_due < datetime.utcnow():
            self.is_overdue = True
        return self.is_overdue

    def __repr__(self):
        return f'<ScheduledInspection {self.inspection_type} due {self.next_due}>'
