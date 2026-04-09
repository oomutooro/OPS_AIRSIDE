"""
Inspection and reporting scheduler helpers.
"""
from datetime import datetime, timedelta
from app import db
from app.models.inspection import ScheduledInspection


class SchedulerService:
    """Schedule and update recurring inspections."""

    FREQUENCY_DELTAS = {
        'daily': timedelta(days=1),
        'weekly': timedelta(weeks=1),
        'monthly': timedelta(days=30),
        'quarterly': timedelta(days=90),
    }

    @classmethod
    def compute_next_due(cls, from_dt: datetime, frequency: str):
        delta = cls.FREQUENCY_DELTAS.get(frequency, timedelta(days=1))
        return from_dt + delta

    @classmethod
    def mark_completed(cls, schedule_id: int, completed_at: datetime = None):
        completed_at = completed_at or datetime.utcnow()
        schedule = db.session.get(ScheduledInspection, schedule_id)
        if not schedule:
            return None
        schedule.last_performed = completed_at
        schedule.next_due = cls.compute_next_due(completed_at, schedule.frequency)
        schedule.is_overdue = False
        db.session.commit()
        return schedule

    @classmethod
    def refresh_overdue_flags(cls):
        now = datetime.utcnow()
        schedules = ScheduledInspection.query.filter_by(is_active=True).all()
        for s in schedules:
            s.is_overdue = bool(s.next_due and s.next_due < now)
        db.session.commit()
        return len(schedules)
