"""
FlightMovement model — local mirror of AODB flight schedule data.
Populated by AodbSyncService; one row per unique AODB flightId.
"""
from datetime import datetime
from app import db


def _parse_aodb_dt(value: str):
    """Parse AODB datetime string (YYYYMMDDHH24MI) to Python datetime, or None."""
    if not value or len(value) < 12:
        return None
    try:
        return datetime.strptime(value[:12], '%Y%m%d%H%M')
    except ValueError:
        return None


class FlightMovement(db.Model):
    """Cached AODB flight movement record (arrival or departure)."""
    __tablename__ = 'flight_movements'

    id = db.Column(db.Integer, primary_key=True)

    # AODB primary key — unique per flight leg
    aodb_flight_id = db.Column(db.String(22), unique=True, nullable=False, index=True)

    # ARR or DEP
    arr_or_dep = db.Column(db.String(3), nullable=False, index=True)

    # Airline / flight identity
    flight_iata_code = db.Column(db.String(8), nullable=True)
    flight_icao_code = db.Column(db.String(8), nullable=True)
    airline_name = db.Column(db.String(128), nullable=True)
    flight_number = db.Column(db.String(16), nullable=True, index=True)
    callsign = db.Column(db.String(12), nullable=True)

    # Schedule
    scheduled_date = db.Column(db.String(8), nullable=True)  # YYYYMMDD
    scheduled_datetime = db.Column(db.DateTime, nullable=True)
    estimated_datetime = db.Column(db.DateTime, nullable=True)
    actual_datetime = db.Column(db.DateTime, nullable=True)   # ATA or ATD

    # Milestones — stored as datetime; field names match AODB doc
    # Arrivals: RPI (ramp in), SPI (stand pull-in), BTI (bridge touch-in)
    # Departures: BTO (bridge touch-out), SPO (stand pull-out), RPO (ramp out)
    milestone_1 = db.Column(db.DateTime, nullable=True)  # RPI / BTO
    milestone_2 = db.Column(db.DateTime, nullable=True)  # SPI / SPO
    milestone_3 = db.Column(db.DateTime, nullable=True)  # BTI / RPO

    # Route
    origin_airport = db.Column(db.String(8), nullable=True)
    destination_airport = db.Column(db.String(8), nullable=True)

    # Ground assignment
    terminal = db.Column(db.String(16), nullable=True)
    stand = db.Column(db.String(16), nullable=True, index=True)

    # AODB live status
    operation_status = db.Column(db.String(32), nullable=True)

    # Sync metadata
    synced_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    raw_payload = db.Column(db.JSON, nullable=True)  # full AODB response for audit

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def upsert_from_aodb(cls, record: dict, arr_or_dep: str) -> 'FlightMovement':
        """
        Insert or update a FlightMovement from one AODB movement record.
        Returns the (possibly new) instance; caller must commit.
        """
        flight_id = (record.get('flightId') or '').strip()
        if not flight_id:
            return None

        obj = cls.query.filter_by(aodb_flight_id=flight_id).first() or cls(
            aodb_flight_id=flight_id
        )

        obj.arr_or_dep = arr_or_dep.upper()
        obj.flight_iata_code   = record.get('flightIataCode')
        obj.flight_icao_code   = record.get('flightIcaoCode')
        obj.airline_name       = record.get('airlineName')
        obj.flight_number      = record.get('flightNumber')
        obj.callsign           = record.get('callsign')
        obj.scheduled_date     = record.get('scheduledDate')
        obj.scheduled_datetime = _parse_aodb_dt(record.get('scheduledTime'))
        obj.estimated_datetime = _parse_aodb_dt(record.get('estimatedTime'))
        obj.terminal           = record.get('terminal')
        obj.stand              = record.get('stand')
        obj.operation_status   = record.get('operationStatus')
        obj.origin_airport     = record.get('originAirport')
        obj.destination_airport = record.get('destinationAirport')
        obj.raw_payload        = record
        obj.synced_at          = datetime.utcnow()

        if arr_or_dep.upper() == 'ARR':
            obj.actual_datetime = _parse_aodb_dt(record.get('ATA'))
            obj.milestone_1     = _parse_aodb_dt(record.get('RPI'))
            obj.milestone_2     = _parse_aodb_dt(record.get('SPI'))
            obj.milestone_3     = _parse_aodb_dt(record.get('BTI'))
        else:
            obj.actual_datetime = _parse_aodb_dt(record.get('ATD'))
            obj.milestone_1     = _parse_aodb_dt(record.get('BTO'))
            obj.milestone_2     = _parse_aodb_dt(record.get('SPO'))
            obj.milestone_3     = _parse_aodb_dt(record.get('RPO'))

        db.session.add(obj)
        return obj

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'aodb_flight_id': self.aodb_flight_id,
            'arr_or_dep': self.arr_or_dep,
            'flight_number': self.flight_number,
            'flight_iata_code': self.flight_iata_code,
            'airline_name': self.airline_name,
            'callsign': self.callsign,
            'scheduled_date': self.scheduled_date,
            'scheduled_datetime': self.scheduled_datetime.isoformat() if self.scheduled_datetime else None,
            'estimated_datetime': self.estimated_datetime.isoformat() if self.estimated_datetime else None,
            'actual_datetime': self.actual_datetime.isoformat() if self.actual_datetime else None,
            'origin_airport': self.origin_airport,
            'destination_airport': self.destination_airport,
            'terminal': self.terminal,
            'stand': self.stand,
            'operation_status': self.operation_status,
            'synced_at': self.synced_at.isoformat() if self.synced_at else None,
        }

    def __repr__(self):
        return f'<FlightMovement {self.arr_or_dep} {self.flight_number} {self.scheduled_date}>'


class AodbWriteback(db.Model):
    """Queue item for writing data back to AODB."""
    __tablename__ = 'aodb_writebacks'

    id = db.Column(db.Integer, primary_key=True)

    # Foreign keys for audit trail
    flight_movement_id = db.Column(db.Integer, db.ForeignKey('flight_movements.id'), nullable=True)
    form_submission_id = db.Column(db.Integer, db.ForeignKey('form_submissions.id'), nullable=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=True)

    # AODB identifiers
    aodb_flight_id = db.Column(db.String(22), nullable=False, index=True)

    # Write-back type and payload
    writeback_type = db.Column(db.String(32), nullable=False, index=True)
    # Examples: 'bridge_docking', 'bridge_backoff', 'stand_assignment'
    # Maps to AODB field names like 'BTI', 'BTO', 'stand', etc.

    aodb_field_name = db.Column(db.String(32), nullable=False)  # 'BTI', 'BTO', 'stand', etc.
    aodb_value = db.Column(db.String(256), nullable=False)      # Stringified value ready for AODB

    # Status tracking
    status = db.Column(db.String(16), default='pending', index=True)
    # pending → in_progress → (completed | failed) → (completed_on_retry | failed_permanent)

    retry_count = db.Column(db.Integer, default=0)
    max_retries = db.Column(db.Integer, default=3)

    # Result tracking
    error_message = db.Column(db.Text, nullable=True)
    aodb_response = db.Column(db.JSON, nullable=True)  # Full AODB response for audit

    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_attempted_at = db.Column(db.DateTime, nullable=True)
    completed_at = db.Column(db.DateTime, nullable=True)

    # Bidirectional relationships
    flight_movement = db.relationship('FlightMovement', backref='writebacks')
    submission = db.relationship('FormSubmission', backref='aodb_writebacks')
    user = db.relationship('User', backref='aodb_writebacks')

    @classmethod
    def queue_writeback(
        cls,
        aodb_flight_id: str,
        writeback_type: str,
        aodb_field_name: str,
        aodb_value: str,
        flight_movement_id: int = None,
        form_submission_id: int = None,
        user_id: int = None,
    ) -> 'AodbWriteback':
        """Create a new write-back queue item. Caller must commit."""
        item = cls(
            aodb_flight_id=aodb_flight_id,
            writeback_type=writeback_type,
            aodb_field_name=aodb_field_name,
            aodb_value=str(aodb_value),
            flight_movement_id=flight_movement_id,
            form_submission_id=form_submission_id,
            user_id=user_id,
            status='pending',
        )
        db.session.add(item)
        return item

    def can_retry(self) -> bool:
        """Check if this item should be retried."""
        return self.status == 'failed' and self.retry_count < self.max_retries

    def to_dict(self) -> dict:
        return {
            'id': self.id,
            'aodb_flight_id': self.aodb_flight_id,
            'writeback_type': self.writeback_type,
            'aodb_field_name': self.aodb_field_name,
            'aodb_value': self.aodb_value,
            'status': self.status,
            'retry_count': self.retry_count,
            'error_message': self.error_message,
            'created_at': self.created_at.isoformat() if self.created_at else None,
            'completed_at': self.completed_at.isoformat() if self.completed_at else None,
        }

    def __repr__(self):
        return f'<AodbWriteback {self.writeback_type} {self.aodb_flight_id} {self.status}>'
