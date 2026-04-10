"""Models package initialization."""
from app.models.user import User, Role
from app.models.reference import Company, Aircraft, AirsideVehicle, AirsidePersonnel, ParkingStand, AirsideLocation
from app.models.form import FormTemplate, FormSubmission, Attachment, AuditLog, IssueWorkflow
from app.models.inspection import ESSTATMotorisedInspection, ESSTATNonMotorisedInspection, FODCleaningRecord, FODWalk, ScheduledInspection
from app.models.permit import ADPApplication, ADPPermit
from app.models.incident import Incident, Violation, ViolationType
from app.models.apron import Shift, ShiftRoster, HandoverReport, StandAllocation
from app.models.flight import FlightMovement

__all__ = [
    'User', 'Role',
    'Company', 'Aircraft', 'AirsideVehicle', 'AirsidePersonnel', 'ParkingStand', 'AirsideLocation',
    'FormTemplate', 'FormSubmission', 'Attachment', 'AuditLog', 'IssueWorkflow',
    'ESSTATMotorisedInspection', 'ESSTATNonMotorisedInspection', 'FODCleaningRecord', 'FODWalk',
    'ScheduledInspection', 'ADPApplication', 'ADPPermit',
    'Incident', 'Violation', 'ViolationType',
    'Shift', 'ShiftRoster', 'HandoverReport', 'StandAllocation',
    'FlightMovement',
]
