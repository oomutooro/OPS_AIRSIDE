"""
Reference data models: Aircraft, Companies, Vehicles, Stands, Locations, Personnel.
"""
from datetime import datetime, date
from app import db


class Company(db.Model):
    """Companies operating at Entebbe Airport airside."""
    __tablename__ = 'companies'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(128), nullable=False)
    code = db.Column(db.String(16), unique=True, nullable=True)
    company_type = db.Column(db.String(32), nullable=False)
    # Types: airline|GHA|fuel|catering|maintenance|security|military|UN|government
    contact_person = db.Column(db.String(128), nullable=True)
    phone = db.Column(db.String(32), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    address = db.Column(db.Text, nullable=True)
    logo_url = db.Column(db.String(256), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    vehicles = db.relationship('AirsideVehicle', backref='company', lazy='dynamic')
    personnel = db.relationship('AirsidePersonnel', backref='company', lazy='dynamic')

    def to_dict(self):
        return {
            'id': self.id,
            'name': self.name,
            'code': self.code,
            'company_type': self.company_type,
            'contact_person': self.contact_person,
            'phone': self.phone,
            'email': self.email,
            'is_active': self.is_active,
        }

    def __repr__(self):
        return f'<Company {self.name}>'


class Aircraft(db.Model):
    """Aircraft reference data."""
    __tablename__ = 'aircraft'

    id = db.Column(db.Integer, primary_key=True)
    registration = db.Column(db.String(16), unique=True, nullable=False, index=True)
    aircraft_type = db.Column(db.String(32), nullable=True)
    operator = db.Column(db.String(128), nullable=True)
    wake_turbulence_category = db.Column(db.String(4), nullable=True)  # A/B/C/D/E/F
    max_takeoff_weight_kg = db.Column(db.Float, nullable=True)
    wingspan_m = db.Column(db.Float, nullable=True)
    length_m = db.Column(db.Float, nullable=True)
    acn = db.Column(db.Float, nullable=True, doc='Aircraft Classification Number')
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Aircraft {self.registration} ({self.aircraft_type})>'


class AirsideVehicle(db.Model):
    """Vehicles and equipment operating on the airside."""
    __tablename__ = 'airside_vehicles'

    id = db.Column(db.Integer, primary_key=True)
    registration = db.Column(db.String(32), unique=True, nullable=False, index=True)
    call_sign = db.Column(db.String(64), nullable=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    vehicle_type = db.Column(db.String(64), nullable=True)
    # e.g. GPU, tug, highloader, fuel dispenser, follow-me, fire truck, ramp bus
    make_model = db.Column(db.String(128), nullable=True)
    year_of_manufacture = db.Column(db.Integer, nullable=True)
    colour = db.Column(db.String(32), nullable=True)
    beacon_colour = db.Column(db.String(16), nullable=True)  # yellow|blue
    adp_code = db.Column(db.String(8), nullable=True)  # brown|green|blue|red
    avp_number = db.Column(db.String(32), nullable=True, doc='Airside Vehicle Permit number')
    avp_expiry = db.Column(db.Date, nullable=True)
    last_essat_date = db.Column(db.Date, nullable=True)
    essat_sticker_no = db.Column(db.String(32), nullable=True)
    essat_sticker_expiry = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    is_grounded = db.Column(db.Boolean, default=False)
    grounded_reason = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    @property
    def essat_is_current(self) -> bool:
        """Check if ESSAT sticker is current."""
        if not self.essat_sticker_expiry:
            return False
        return self.essat_sticker_expiry >= date.today()

    @property
    def avp_is_current(self) -> bool:
        """Check if AVP is current."""
        if not self.avp_expiry:
            return False
        return self.avp_expiry >= date.today()

    def to_dict(self):
        return {
            'id': self.id,
            'registration': self.registration,
            'call_sign': self.call_sign,
            'company_id': self.company_id,
            'vehicle_type': self.vehicle_type,
            'make_model': self.make_model,
            'colour': self.colour,
            'beacon_colour': self.beacon_colour,
            'adp_code': self.adp_code,
            'last_essat_date': self.last_essat_date.isoformat() if self.last_essat_date else None,
            'essat_sticker_no': self.essat_sticker_no,
            'essat_is_current': self.essat_is_current,
            'avp_is_current': self.avp_is_current,
            'is_active': self.is_active,
            'is_grounded': self.is_grounded,
        }

    def __repr__(self):
        return f'<AirsideVehicle {self.registration}>'


class AirsidePersonnel(db.Model):
    """Personnel holding Airside Driving Permits."""
    __tablename__ = 'airside_personnel'

    id = db.Column(db.Integer, primary_key=True)
    badge_number = db.Column(db.String(32), unique=True, nullable=False, index=True)
    full_name = db.Column(db.String(128), nullable=False)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=True)
    job_title = db.Column(db.String(64), nullable=True)
    phone = db.Column(db.String(32), nullable=True)
    email = db.Column(db.String(120), nullable=True)
    national_driving_license_no = db.Column(db.String(32), nullable=True)
    ndl_expiry = db.Column(db.Date, nullable=True)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            'id': self.id,
            'badge_number': self.badge_number,
            'full_name': self.full_name,
            'company_id': self.company_id,
            'job_title': self.job_title,
            'national_driving_license_no': self.national_driving_license_no,
            'ndl_expiry': self.ndl_expiry.isoformat() if self.ndl_expiry else None,
            'is_active': self.is_active,
        }

    def __repr__(self):
        return f'<AirsidePersonnel {self.badge_number} - {self.full_name}>'


class ParkingStand(db.Model):
    """Aircraft parking stands at Entebbe (Aprons 1, 2, 4, 5)."""
    __tablename__ = 'parking_stands'

    id = db.Column(db.Integer, primary_key=True)
    stand_code = db.Column(db.String(16), unique=True, nullable=False, index=True)
    # e.g. A1S01, A2S03, A5S51A
    stand_number = db.Column(db.String(8), nullable=False)
    apron = db.Column(db.String(4), nullable=False)  # 1|2|4|5
    category = db.Column(db.String(4), nullable=True)  # A|B|C|E|F (aircraft size codes)
    aircraft_compatibility = db.Column(db.JSON, default=list)
    # e.g. ["B737", "A320", "B767", "B777", "A380"]
    has_pbb = db.Column(db.Boolean, default=False, doc='Has Passenger Boarding Bridge')
    pbb_number = db.Column(db.String(16), nullable=True)
    latitude = db.Column(db.Float, nullable=True)
    longitude = db.Column(db.Float, nullable=True)
    pcr = db.Column(db.Float, nullable=True, doc='Pavement Classification Rating')
    pavement_type = db.Column(db.String(16), nullable=True)  # flexible|rigid
    is_active = db.Column(db.Boolean, default=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # Stop mark definitions by aircraft code
    STOP_MARKS = {
        'A': 'Aircraft code A: B737, A320 family',
        'B': 'Aircraft code B: B767, A310 family',
        'C': 'Aircraft code C: B777, A330, A340, A350, B747-800 family',
        'E': 'Aircraft code E: A320neo, B737 MAX family',
        'F': 'Aircraft code F: A380 (Code F - requires wing walkers)',
    }

    def to_dict(self):
        return {
            'id': self.id,
            'stand_code': self.stand_code,
            'stand_number': self.stand_number,
            'apron': self.apron,
            'category': self.category,
            'has_pbb': self.has_pbb,
            'is_active': self.is_active,
        }

    def __repr__(self):
        return f'<ParkingStand {self.stand_code} (Apron {self.apron})>'


class AirsideLocation(db.Model):
    """Named locations on the airside: taxiways, runways, aprons, perimeter."""
    __tablename__ = 'airside_locations'

    id = db.Column(db.Integer, primary_key=True)
    code = db.Column(db.String(16), unique=True, nullable=False, index=True)
    name = db.Column(db.String(128), nullable=False)
    zone = db.Column(db.String(32), nullable=False)
    # Zone: apron|taxiway|runway|perimeter|terminal|cargo|fuel_farm
    description = db.Column(db.Text, nullable=True)
    is_active = db.Column(db.Boolean, default=True)

    # Taxiway specifics
    TAXIWAYS = ['A1', 'A2', 'A3', 'A4', 'B', 'C1', 'C2', 'C3', 'D', 'H1', 'J1', 'J2', 'J3']
    RUNWAYS = ['17/35', '12/30']

    def __repr__(self):
        return f'<AirsideLocation {self.code} ({self.zone})>'


class EquipmentInventory(db.Model):
    """
    Equipment inventory submitted by companies prior to ESSAT inspection cycles.
    Covers both motorised and non-motorised equipment.
    Linked to FormSubmission via inspection_submission_id once inspected.
    """
    __tablename__ = 'equipment_inventory'

    id = db.Column(db.Integer, primary_key=True)
    company_id = db.Column(db.Integer, db.ForeignKey('companies.id'), nullable=False, index=True)
    # Inspection cycle identifier, e.g. "2026-Q1" or "2026"
    inspection_cycle = db.Column(db.String(16), nullable=False, index=True)
    equipment_type = db.Column(db.String(16), nullable=False, default='motorised')
    # 'motorised' | 'non-motorised'
    registration = db.Column(db.String(64), nullable=True)
    description = db.Column(db.String(256), nullable=True)
    make_model = db.Column(db.String(128), nullable=True)
    year_of_manufacture = db.Column(db.Integer, nullable=True)
    # Linked inspection form submission (once inspected)
    inspection_submission_id = db.Column(db.Integer, db.ForeignKey('form_submissions.id'), nullable=True)
    # Holds FormSubmission.id of the ESSAT inspection result, when inspected
    submitted_date = db.Column(db.Date, default=date.today, nullable=False)
    submitted_by = db.Column(db.String(128), nullable=True)
    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    company = db.relationship('Company', backref=db.backref('equipment_inventory', lazy='dynamic'))

    @property
    def is_inspected(self):
        return self.inspection_submission_id is not None

    def to_dict(self):
        return {
            'id': self.id,
            'company_id': self.company_id,
            'company_name': self.company.name if self.company else None,
            'inspection_cycle': self.inspection_cycle,
            'equipment_type': self.equipment_type,
            'registration': self.registration,
            'description': self.description,
            'make_model': self.make_model,
            'year_of_manufacture': self.year_of_manufacture,
            'is_inspected': self.is_inspected,
            'submitted_date': self.submitted_date.isoformat() if self.submitted_date else None,
            'submitted_by': self.submitted_by,
        }

    def __repr__(self):
        return f'<EquipmentInventory {self.registration or self.description} ({self.inspection_cycle})>'
