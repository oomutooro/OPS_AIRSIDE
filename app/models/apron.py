"""
Apron operations models: Shifts, Handover Reports, Stand Allocations.
"""
from datetime import datetime, date
from app import db


class Shift(db.Model):
    """Shift records for apron operations team."""
    __tablename__ = 'shifts'

    id = db.Column(db.Integer, primary_key=True)
    shift_date = db.Column(db.Date, nullable=False, index=True)
    shift_type = db.Column(db.String(16), nullable=False)  # day|night
    # Day shift: 06:00-18:00, Night shift: 18:00-06:00
    start_time = db.Column(db.Time, nullable=True)
    end_time = db.Column(db.Time, nullable=True)

    # Shift leader
    leader_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    leader_name = db.Column(db.String(128), nullable=True)

    # Team members (JSON list of {user_id, name, badge, role, station})
    members = db.Column(db.JSON, default=list)

    # Attendance
    attending_count = db.Column(db.Integer, default=0)
    absent_apron5 = db.Column(db.Integer, default=0)
    absent_apron4 = db.Column(db.Integer, default=0)
    absent_apron_tower = db.Column(db.Integer, default=0)

    # Equipment status (JSON list of {item, status, issues})
    equipment_status = db.Column(db.JSON, default=list)

    # Office tools status (JSON)
    office_tools = db.Column(db.JSON, default=dict)

    # Operations summary
    incidents_summary = db.Column(db.Text, nullable=True)
    issues_reported = db.Column(db.Text, nullable=True)
    handover_notes = db.Column(db.Text, nullable=True)

    # Weather during shift
    weather_start = db.Column(db.String(64), nullable=True)
    weather_end = db.Column(db.String(64), nullable=True)

    status = db.Column(db.String(16), default='active')  # active|completed|cancelled
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    leader = db.relationship('User', backref='led_shifts')

    def to_dict(self):
        return {
            'id': self.id,
            'shift_date': self.shift_date.isoformat(),
            'shift_type': self.shift_type,
            'leader_name': self.leader_name,
            'members': self.members,
            'status': self.status,
        }

    def __repr__(self):
        return f'<Shift {self.shift_date} {self.shift_type}>'


class ShiftRoster(db.Model):
    """Per-user duty roster entry used to enforce who is on duty for forms/signatures."""
    __tablename__ = 'shift_roster'

    id = db.Column(db.Integer, primary_key=True)
    duty_date = db.Column(db.Date, nullable=False, index=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False, index=True)
    duty_type = db.Column(db.String(16), nullable=False)  # day|night|off
    cycle_day_index = db.Column(db.Integer, nullable=False, default=0)
    # Cycle index mapping: 0=day, 1=night, 2=off, 3=off
    notes = db.Column(db.String(256), nullable=True)
    created_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    user = db.relationship('User', foreign_keys=[user_id], backref='shift_roster_entries')
    created_by = db.relationship('User', foreign_keys=[created_by_user_id])

    __table_args__ = (
        db.UniqueConstraint('duty_date', 'user_id', name='uq_shift_roster_date_user'),
    )

    CYCLE = ['day', 'night', 'off', 'off']

    @classmethod
    def duty_for_index(cls, idx: int) -> str:
        return cls.CYCLE[idx % len(cls.CYCLE)]

    @classmethod
    def index_for_duty(cls, duty_type: str) -> int:
        duty_type = (duty_type or '').lower()
        if duty_type not in cls.CYCLE:
            return 0
        return cls.CYCLE.index(duty_type)

    def __repr__(self):
        return f'<ShiftRoster {self.duty_date} user={self.user_id} duty={self.duty_type}>'


class HandoverReport(db.Model):
    """Form 2 - Shift Handover/Takeover Report."""
    __tablename__ = 'handover_reports'

    id = db.Column(db.Integer, primary_key=True)
    reference_no = db.Column(db.String(32), unique=True, nullable=True)
    handover_date = db.Column(db.Date, nullable=False, index=True)
    handover_time = db.Column(db.Time, nullable=True)

    outgoing_shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=True)
    incoming_shift_id = db.Column(db.Integer, db.ForeignKey('shifts.id'), nullable=True)

    # Vehicle/equipment status (JSON list of items)
    vehicles_equipment = db.Column(db.JSON, default=list)

    # Office tools (JSON: {item: status})
    office_tools = db.Column(db.JSON, default=dict)

    # Major events during outgoing shift
    major_events = db.Column(db.Text, nullable=True)
    pending_issues = db.Column(db.Text, nullable=True)

    # Outgoing shift rep
    outgoing_name = db.Column(db.String(128), nullable=True)
    outgoing_badge = db.Column(db.String(32), nullable=True)
    outgoing_sign = db.Column(db.Text, nullable=True)  # base64 signature
    outgoing_sign_time = db.Column(db.DateTime, nullable=True)

    # Incoming shift rep
    incoming_name = db.Column(db.String(128), nullable=True)
    incoming_badge = db.Column(db.String(32), nullable=True)
    incoming_sign = db.Column(db.Text, nullable=True)
    incoming_sign_time = db.Column(db.DateTime, nullable=True)

    status = db.Column(db.String(32), default='pending')
    # pending|outgoing_signed|incoming_signed|complete

    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    outgoing_shift = db.relationship('Shift', foreign_keys=[outgoing_shift_id], backref='outgoing_handover')
    incoming_shift = db.relationship('Shift', foreign_keys=[incoming_shift_id], backref='incoming_handover')

    def __repr__(self):
        return f'<HandoverReport {self.reference_no} {self.handover_date}>'


class StandAllocation(db.Model):
    """Aircraft stand allocation tracking with Form 3 (Apron Parking Reference)."""
    __tablename__ = 'stand_allocations'

    id = db.Column(db.Integer, primary_key=True)
    allocation_date = db.Column(db.Date, nullable=False, index=True)
    flight_number = db.Column(db.String(16), nullable=True)
    aircraft_registration = db.Column(db.String(16), nullable=True)
    aircraft_type = db.Column(db.String(32), nullable=True)
    aircraft_size_code = db.Column(db.String(4), nullable=True)  # A|B|C|E|F
    airline_operator = db.Column(db.String(128), nullable=True)

    # Times (UTC)
    eta = db.Column(db.DateTime, nullable=True, doc='Estimated Time of Arrival')
    etd = db.Column(db.DateTime, nullable=True, doc='Estimated Time of Departure')
    ata = db.Column(db.DateTime, nullable=True, doc='Actual Time of Arrival')
    atd = db.Column(db.DateTime, nullable=True, doc='Actual Time of Departure')

    # Stand details
    stand_id = db.Column(db.Integer, db.ForeignKey('parking_stands.id'), nullable=True)
    allocated_stand_code = db.Column(db.String(16), nullable=True)
    requested_stand_code = db.Column(db.String(16), nullable=True)
    has_pbb = db.Column(db.Boolean, default=False)

    # Allocation type
    flight_type = db.Column(db.String(32), nullable=True)
    # scheduled|non_scheduled|cargo|vvip|military|emergency|ferry
    is_vvip = db.Column(db.Boolean, default=False)
    vvip_details = db.Column(db.Text, nullable=True)

    # Follow Me requirements
    requires_follow_me = db.Column(db.Boolean, default=False)
    follow_me_unit = db.Column(db.String(32), nullable=True)

    # Officers deployed
    marshaller_name = db.Column(db.String(128), nullable=True)
    wing_walker_required = db.Column(db.Boolean, default=False)
    wing_walker_names = db.Column(db.JSON, default=list)

    allocated_by_user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)
    status = db.Column(db.String(32), default='allocated')
    # allocated|arrived|departed|cancelled|diverted

    notes = db.Column(db.Text, nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    stand = db.relationship('ParkingStand', backref='allocations')
    allocated_by = db.relationship('User', backref='stand_allocations')

    def to_dict(self):
        return {
            'id': self.id,
            'flight_number': self.flight_number,
            'aircraft_registration': self.aircraft_registration,
            'aircraft_type': self.aircraft_type,
            'allocated_stand_code': self.allocated_stand_code,
            'eta': self.eta.isoformat() if self.eta else None,
            'etd': self.etd.isoformat() if self.etd else None,
            'status': self.status,
        }

    def __repr__(self):
        return f'<StandAllocation {self.flight_number} -> {self.allocated_stand_code}>'
