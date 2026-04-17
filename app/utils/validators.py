"""
Custom validation utilities for airside business rules.
"""
from datetime import date
from app.utils.constants import SPEED_LIMITS


def validate_speed(zone: str, speed_kmh: float) -> tuple[bool, str]:
    """Validate speed against zone-specific speed limits."""
    limits = {
        'near_aircraft': SPEED_LIMITS['within_15m_of_aircraft'],
        'vehicle_corridor': SPEED_LIMITS['vehicle_corridor'],
        'perimeter': SPEED_LIMITS['perimeter_roads'],
    }
    if zone not in limits:
        return False, 'Unknown zone for speed validation.'

    max_speed = limits[zone]
    if speed_kmh > max_speed:
        return False, f'Speed violation: {speed_kmh} km/h exceeds limit of {max_speed} km/h.'

    return True, 'Speed is within allowed limit.'


def validate_adp_validity(issue_date: date, expiry_date: date) -> tuple[bool, str]:
    """Validate ADP validity period (2 years)."""
    if not issue_date or not expiry_date:
        return False, 'Issue date and expiry date are required.'

    days = (expiry_date - issue_date).days
    if days < 700 or days > 760:
        return False, 'ADP validity should be approximately 2 years.'

    return True, 'ADP validity period is correct.'


def validate_grf_interval(last_report_time, current_report_time) -> tuple[bool, str]:
    """Validate GRF reporting interval (every 30 minutes during rain)."""
    if not last_report_time or not current_report_time:
        return True, 'Initial report accepted.'

    delta_mins = (current_report_time - last_report_time).total_seconds() / 60
    if delta_mins > 35:
        return False, f'GRF report interval too long: {delta_mins:.1f} minutes.'

    return True, 'GRF interval compliant.'


def validate_two_strikes_warning(punch_count: int) -> tuple[bool, str]:
    """Evaluate ADP punch count according to three-strikes rule."""
    if punch_count >= 3:
        return False, 'ADP must be suspended (third strike reached).'
    if punch_count == 2:
        return True, 'Warning: one more strike leads to suspension.'
    return True, 'ADP status acceptable.'
