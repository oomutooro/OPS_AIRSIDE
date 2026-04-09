"""
Dashboard analytics aggregation service.
"""
from datetime import date, timedelta
from sqlalchemy import func
from app.models.form import FormSubmission
from app.models.incident import Violation, Incident
from app.models.inspection import FODCleaningRecord, ESSTATMotorisedInspection
from app.models.apron import StandAllocation


class AnalyticsService:
    """Compute KPI and trend metrics for dashboard/reporting."""

    @staticmethod
    def get_dashboard_kpis():
        today = date.today()
        seven_days_ago = today - timedelta(days=7)

        movements_today = StandAllocation.query.filter(
            StandAllocation.allocation_date == today
        ).count()

        active_inspections = FormSubmission.query.filter(
            FormSubmission.status.in_(['draft', 'submitted'])
        ).count()

        pending_violations = Violation.query.filter(
            Violation.status.in_(['open', 'acknowledged', 'payment_pending'])
        ).count()

        fod_collected = FODCleaningRecord.query.with_entities(
            func.coalesce(func.sum(FODCleaningRecord.total_weight_kg), 0)
        ).filter(FODCleaningRecord.cleaning_date >= seven_days_ago).scalar() or 0

        essat_total = ESSTATMotorisedInspection.query.filter(
            ESSTATMotorisedInspection.inspection_date >= seven_days_ago
        ).count()
        essat_pass = ESSTATMotorisedInspection.query.filter(
            ESSTATMotorisedInspection.inspection_date >= seven_days_ago,
            ESSTATMotorisedInspection.outcome == 'pass'
        ).count()
        essat_rate = round((essat_pass / essat_total) * 100, 1) if essat_total else 0.0

        return {
            'today_movements': movements_today,
            'active_inspections': active_inspections,
            'pending_violations': pending_violations,
            'fod_collected_kg': round(float(fod_collected), 2),
            'essat_compliance_rate': essat_rate,
        }

    @staticmethod
    def incident_trend(days=7):
        start = date.today() - timedelta(days=days - 1)
        rows = Incident.query.with_entities(
            Incident.occurrence_date,
            func.count(Incident.id)
        ).filter(Incident.occurrence_date >= start).group_by(Incident.occurrence_date).all()

        data = {str(r[0]): r[1] for r in rows}
        labels = []
        values = []
        for i in range(days):
            d = start + timedelta(days=i)
            labels.append(d.strftime('%d %b'))
            values.append(data.get(str(d), 0))
        return {'labels': labels, 'values': values}
