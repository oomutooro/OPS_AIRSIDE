"""
Business validation service for forms and operational rules.
"""
from app.utils.constants import SPEED_LIMITS


class ValidationService:
    """Apply domain validation rules across modules."""

    @staticmethod
    def validate_violation_payload(payload: dict):
        errors = []
        required = ['violation_description', 'violation_date', 'violation_location']
        for field in required:
            if not payload.get(field):
                errors.append(f'{field} is required.')
        return errors

    @staticmethod
    def validate_speed_zone(speed_kmh: float, zone_key: str):
        zone_map = {
            'near_aircraft': 'within_15m_of_aircraft',
            'vehicle_corridor': 'vehicle_corridor',
            'perimeter': 'perimeter_roads',
        }
        if zone_key not in zone_map:
            return False, 'Invalid zone key.'
        limit = SPEED_LIMITS[zone_map[zone_key]]
        if speed_kmh > limit:
            return False, f'Exceeded speed limit {limit} km/h for {zone_key}.'
        return True, 'OK'

    @staticmethod
    def validate_adp_test_score(score):
        try:
            score = float(score)
        except (TypeError, ValueError):
            return False, 'Invalid test score.'
        if score < 70:
            return False, 'Pass mark is 70%.'
        return True, 'Eligible.'
