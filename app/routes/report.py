"""
Reporting routes: daily ops report, weekly airside report, analytics dashboard, custom report builder, exports.
"""
from collections import Counter
from io import BytesIO
from datetime import date, datetime, timedelta
from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from app import db
from app.models.form import FormSubmission, FormTemplate
from app.models.flight import FlightMovement
from app.models.apron import HandoverReport
from app.models.incident import Incident, Violation
from app.models.reference import Company
from app.services.export_service import ExportService
from app.services.analytics_service import AnalyticsService
from app.services.aodb_sync import AodbSyncService
from app.services.pdf_generator import PDFGeneratorService
from app.services.workflow_service import WorkflowService
from flask_login import current_user

report_bp = Blueprint('report', __name__)


LEGEND_CODE_TO_INTERACTION = {
    'A': 'EQUIPMENT TO EQUIPMENT',
    'B': 'EQUIPMENT TO AIRCRAFT',
    'C': 'EQUIPMENT TO PERSONNEL',
    'D': 'EQUIPMENT TO PROPERTY',
    'E': 'EQUIPMENT TO PASSENGER',
    'F': 'AIRCRAFT TO EQUIPMENT',
    'G': 'AIRCRAFT TO AIRCRAFT',
    'H': 'AIRCRAFT TO PERSONNEL',
    'I': 'AIRCRAFT TO PROPERTY',
    'J': 'AIRCRAFT TO PASSENGER',
    'K': 'PERSONNEL TO EQUIPMENT',
    'L': 'PERSONNEL TO AIRCRAFT',
    'M': 'PERSONNEL TO PERSONNEL',
    'N': 'PERSONNEL TO PROPERTY',
    'O': 'PERSONNEL TO PASSENGER',
    'P': 'PROPERTY TO EQUIPMENT',
    'Q': 'PROPERTY TO AIRCRAFT',
    'R': 'PROPERTY TO PERSONNEL',
    'S': 'PROPERTY TO PROPERTY',
    'T': 'PROPERTY TO PASSENGER',
    # Others-as-cause extended series
    'X1': 'OTHERS TO EQUIPMENT',
    'X2': 'OTHERS TO AIRCRAFT',
    'X3': 'OTHERS TO PERSONNEL',
    'X4': 'OTHERS TO PROPERTY',
    'X5': 'OTHERS TO PASSENGER',
    'X6': 'OTHERS TO OTHERS',
}


def _quarter_label(dt: date) -> str:
    q = (dt.month - 1) // 3 + 1
    return f'{dt.year}-Q{q}'


def _safe_date_from_submission(submission, field_name='occurrence_date'):
    data = submission.data or {}
    raw = (data.get(field_name) or '').strip()
    if raw:
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            pass
    if submission.submission_date:
        return submission.submission_date
    return submission.created_at.date()


def _parse_date(value, fallback=None):
    raw = (value or '').strip()
    if raw:
        try:
            return datetime.fromisoformat(raw).date()
        except ValueError:
            pass
    return fallback or date.today()


def _start_of_week(anchor_date: date) -> date:
    return anchor_date - timedelta(days=anchor_date.weekday())


def _week_window(anchor_date: date):
    week_start = _start_of_week(anchor_date)
    week_end = week_start + timedelta(days=6)
    return week_start, week_end


def _flight_counts_for_day(day: date):
    day_key = day.strftime('%Y%m%d')
    flights = FlightMovement.query.filter(FlightMovement.scheduled_date == day_key).all()
    arrivals = sum(1 for flight in flights if (flight.arr_or_dep or '').upper() == 'ARR')
    departures = sum(1 for flight in flights if (flight.arr_or_dep or '').upper() == 'DEP')
    return {
        'date': day,
        'date_label': day.strftime('%a, %d %b %Y'),
        'arrivals': arrivals,
        'departures': departures,
        'total': arrivals + departures,
    }


def _count_flights_between(start_date: date, end_date: date):
    start_key = start_date.strftime('%Y%m%d')
    end_key = end_date.strftime('%Y%m%d')
    arrivals = FlightMovement.query.filter(
        FlightMovement.scheduled_date >= start_key,
        FlightMovement.scheduled_date <= end_key,
        FlightMovement.arr_or_dep == 'ARR',
    ).count()
    departures = FlightMovement.query.filter(
        FlightMovement.scheduled_date >= start_key,
        FlightMovement.scheduled_date <= end_key,
        FlightMovement.arr_or_dep == 'DEP',
    ).count()
    return arrivals, departures, arrivals + departures


def _weekly_activity_rows(start_dt: datetime, end_dt: datetime):
    submissions = FormSubmission.query.join(FormTemplate).filter(
        FormSubmission.created_at >= start_dt,
        FormSubmission.created_at < end_dt,
    ).order_by(FormSubmission.created_at.asc()).all()

    breakdown = Counter()
    rows = []
    for submission in submissions:
        form_number = submission.template.form_number if submission.template else None
        breakdown[form_number] += 1
        rows.append({
            'submission': submission,
            'form_number': form_number,
            'title': submission.template.title if submission.template else 'Unknown Form',
            'created_at': submission.created_at,
            'reference_number': submission.reference_number or f'SUB-{submission.id}',
        })

    top_forms = []
    for form_number, count in breakdown.most_common():
        template = FormTemplate.query.filter_by(form_number=form_number).first() if form_number else None
        top_forms.append({
            'form_number': form_number,
            'title': template.title if template else 'Unknown Form',
            'count': count,
        })

    return rows, top_forms


def _submission_week_date(submission: FormSubmission):
    if submission.submission_date:
        return submission.submission_date
    return submission.created_at.date() if submission.created_at else None


def _submission_text_blob(submission: FormSubmission) -> str:
    """Flatten submission payload to lowercase text for keyword scanning."""
    data = submission.data or {}
    chunks = []

    def walk(value):
        if isinstance(value, dict):
            for v in value.values():
                walk(v)
        elif isinstance(value, list):
            for v in value:
                walk(v)
        elif value is None:
            return
        else:
            chunks.append(str(value))

    walk(data)
    return ' '.join(chunks).lower()


def _safe_extract(data: dict, *keys):
    for key in keys:
        value = (data.get(key) or '').strip() if isinstance(data, dict) else ''
        if value:
            return value
    return ''


def _incident_weekly_summary(week_start: date, week_end: date):
    incidents = Incident.query.filter(
        Incident.occurrence_date >= week_start,
        Incident.occurrence_date <= week_end,
    ).order_by(Incident.occurrence_date.asc(), Incident.created_at.asc()).all()

    phase_counts = Counter()
    rows = []
    for inc in incidents:
        weather = inc.weather_conditions or {}
        phase = (weather.get('phase_of_operation') or '').strip() or 'Unspecified'
        phase_counts[phase] += 1
        rows.append({
            'date': inc.occurrence_date,
            'incident_type': (inc.incident_type or 'incident').replace('_', ' ').title(),
            'severity': (inc.severity or 'minor').title(),
            'phase': phase,
            'location': inc.location or 'Unspecified location',
            'description': (inc.description or '').strip(),
            'flight_number': inc.flight_number or '',
            'airline': inc.airline_operator or '',
        })

    return rows, phase_counts


def _handover_weekly_summary(week_start: date, week_end: date):
    handovers = HandoverReport.query.filter(
        HandoverReport.handover_date >= week_start,
        HandoverReport.handover_date <= week_end,
    ).order_by(HandoverReport.handover_date.asc(), HandoverReport.created_at.asc()).all()

    rows = []
    for h in handovers:
        rows.append({
            'date': h.handover_date,
            'reference': h.reference_no or f'HDR-{h.id}',
            'major_events': (h.major_events or '').strip(),
            'pending_issues': (h.pending_issues or '').strip(),
            'outgoing': h.outgoing_name or '',
            'incoming': h.incoming_name or '',
        })
    return rows


def _violation_weekly_summary(week_start: date, week_end: date):
    violations = Violation.query.filter(
        Violation.violation_date >= week_start,
        Violation.violation_date <= week_end,
    ).order_by(Violation.violation_date.asc(), Violation.created_at.asc()).all()

    rows = []
    for v in violations:
        company = ''
        if v.offender_company:
            company = v.offender_company.name
        rows.append({
            'date': v.violation_date,
            'reference': v.violation_number or f'VIO-{v.id}',
            'person': v.offender_name or 'Unspecified',
            'company': company or 'Unspecified',
            'description': (v.violation_description or '').strip(),
            'status': (v.status or 'open').replace('_', ' ').title(),
        })
    return rows


def _inspection_and_ops_weekly_summary(week_start: date, week_end: date):
    forms = FormSubmission.query.join(FormTemplate).filter(
        FormSubmission.created_at >= datetime.combine(week_start, datetime.min.time()),
        FormSubmission.created_at < datetime.combine(week_end + timedelta(days=1), datetime.min.time()),
    ).order_by(FormSubmission.created_at.asc()).all()

    inspection_keywords = (
        'runway', 'pothole', 'crack', 'surface', 'fod', 'fuel', 'spillage',
        'unserviceable', 'fault', 'defect', 'ac', 'air conditioning', 'bridge', 'tpbb',
    )
    works_keywords = ('painting', 'repair', 'surface repair', 'slashing', 'works', 'maintenance', 'marking')

    inspection_rows = []
    tpbb_issue_rows = []
    works_rows = []

    for sub in forms:
        data = sub.data or {}
        form_no = sub.template.form_number if sub.template else None
        title = sub.template.title if sub.template else 'Unknown Form'
        text_blob = _submission_text_blob(sub)

        note = _safe_extract(
            data,
            'remarks', 'notes', 'issues', 'pending_issues', 'major_events',
            'observations', 'findings', 'defects', 'description',
        )

        if form_no in {4, 6, 7, 8, 9, 20, 21, 22, 24, 25, 18, 19} or any(k in text_blob for k in inspection_keywords):
            inspection_rows.append({
                'date': _submission_week_date(sub),
                'form_number': form_no,
                'title': title,
                'reference': sub.reference_number or f'SUB-{sub.id}',
                'summary': note or 'Inspection/operational finding recorded.',
            })

        if form_no == 5 and any(k in text_blob for k in ('unserviceable', 'fault', 'defect', 'ac', 'air conditioning', 'bridge')):
            tpbb_issue_rows.append({
                'date': _submission_week_date(sub),
                'reference': sub.reference_number or f'SUB-{sub.id}',
                'flight_number': _safe_extract(data, 'flight_number'),
                'bridge_no': _safe_extract(data, 'bridge_no'),
                'summary': note or 'TPBB issue captured in remarks.',
            })

        if any(k in text_blob for k in works_keywords):
            works_rows.append({
                'date': _submission_week_date(sub),
                'reference': sub.reference_number or f'SUB-{sub.id}',
                'form_number': form_no,
                'title': title,
                'summary': note or 'Airside works activity recorded.',
            })

    return inspection_rows, tpbb_issue_rows, works_rows


def _ensure_weekly_airside_form_template():
    template = FormTemplate.query.filter_by(form_number=26).first()
    if template:
        return template, False

    template = FormTemplate(
        form_number=26,
        title='Weekly Airside Report',
        description='Weekly report for airside activity, flights, incidents, and passenger totals.',
        category='report',
        route_endpoint='report.weekly_airside_report',
        is_active=True,
        requires_signature=False,
        requires_approval=False,
        allowed_roles=['admin', 'supervisor', 'inspector', 'operator'],
    )
    db.session.add(template)
    db.session.flush()
    return template, True


def _weekly_airside_payload(anchor_date: date):
    week_start, week_end = _week_window(anchor_date)
    week_start_dt = datetime.combine(week_start, datetime.min.time())
    week_end_dt = datetime.combine(week_end + timedelta(days=1), datetime.min.time())

    pob_week = AodbSyncService.pob_stats_for_range(week_start, week_end)
    daily_rows = [
        {
            'date': row['date'],
            'date_label': row['date'].strftime('%a, %d %b %Y'),
            'arrivals': row['arrivals'],
            'departures': row['departures'],
            'total': row['total_flights'],
            'pob_arrivals': row['pob_arrivals'],
            'pob_departures': row['pob_departures'],
            'pob_total': row['pob_total'],
        }
        for row in pob_week['daily']
    ]
    week_arrivals = pob_week['arrivals']
    week_departures = pob_week['departures']
    week_total = pob_week['total_flights']
    week_pob_arrivals = pob_week['pob_arrivals']
    week_pob_departures = pob_week['pob_departures']
    week_pob_total = pob_week['pob_total']

    incident_rows, phase_counts = _incident_weekly_summary(week_start, week_end)
    handover_rows = _handover_weekly_summary(week_start, week_end)
    violation_rows = _violation_weekly_summary(week_start, week_end)
    inspection_rows, tpbb_issue_rows, works_rows = _inspection_and_ops_weekly_summary(week_start, week_end)

    activity_rows, top_forms = _weekly_activity_rows(week_start_dt, week_end_dt)
    latest_weekly_report = FormSubmission.query.join(FormTemplate).filter(
        FormTemplate.form_number == 26,
        FormSubmission.created_at >= week_start_dt,
        FormSubmission.created_at < week_end_dt,
    ).order_by(FormSubmission.created_at.desc()).first()

    return {
        'anchor_date': anchor_date,
        'week_start': week_start,
        'week_end': week_end,
        'daily_rows': daily_rows,
        'week_arrivals': week_arrivals,
        'week_departures': week_departures,
        'week_total': week_total,
        'week_pob_arrivals': week_pob_arrivals,
        'week_pob_departures': week_pob_departures,
        'week_pob_total': week_pob_total,
        'incident_count': len(incident_rows),
        'incident_rows': incident_rows,
        'phase_counts': dict(phase_counts.most_common()),
        'handover_rows': handover_rows,
        'violation_rows': violation_rows,
        'inspection_rows': inspection_rows,
        'tpbb_issue_rows': tpbb_issue_rows,
        'works_rows': works_rows,
        'activity_rows': activity_rows,
        'activity_total': len(activity_rows),
        'top_forms': top_forms,
        'latest_weekly_report': latest_weekly_report,
    }


def _is_checked(value) -> bool:
    if isinstance(value, bool):
        return value
    raw = str(value or '').strip().lower()
    return raw in ('1', 'true', 'yes', 'y', 'on', 'checked')


def _normalize_incident_cause(value):
    raw = (value or '').strip().lower()
    mapping = {
        'bird strike': 'BIRD STRIKE',
        'bird_strike': 'BIRD STRIKE',
        'human error': 'HUMAN ERROR',
        'human_error': 'HUMAN ERROR',
        'bad weather': 'BAD WEATHER',
        'weather': 'BAD WEATHER',
        'medical': 'MEDICAL',
        'passenger misconduct': 'PASSENGER MISCONDUCT',
        'passenger_misconduct': 'PASSENGER MISCONDUCT',
        'tyre burst': 'TYRE BURST',
        'tyre_burst': 'TYRE BURST',
        'passenger cause': 'PASSENGER CAUSE',
        'passenger_cause': 'PASSENGER CAUSE',
        'airport environment': 'AIRPORT ENVIRONMENT',
        'airport_environment': 'AIRPORT ENVIRONMENT',
        'fod': 'FOD',
        'wildlife': 'WILDLIFE',
        'technical problem': 'TECHNICAL PROBLEM',
        'technical issue': 'TECHNICAL PROBLEM',
        'technical fault': 'TECHNICAL PROBLEM',
        'system fault': 'TECHNICAL PROBLEM',
        'mechanical failure': 'TECHNICAL PROBLEM',
        'apu fault': 'TECHNICAL PROBLEM',
        'smoking apu': 'TECHNICAL PROBLEM',
    }
    if raw in mapping:
        return mapping[raw]
    return (value or 'OTHER').strip().upper() or 'OTHER'


def _normalize_incident_legend(value):
    raw = (value or '').strip().lower()
    mapping = {
        'accident': 'ACCIDENT',
        'incident': 'INCIDENT',
        'near_miss': 'NEAR MISS',
        'near miss': 'NEAR MISS',
        'runway_incursion': 'RUNWAY INCURSION',
        'runway incursion': 'RUNWAY INCURSION',
        'bird_strike': 'BIRD STRIKE',
        'bird strike': 'BIRD STRIKE',
        'wildlife': 'WILDLIFE',
        'other': 'INCIDENT',
    }
    return mapping.get(raw, (value or 'OTHER').strip().upper() or 'OTHER')


def _normalize_interaction(data):
    explicit = (data.get('interaction_category') or '').strip().upper()
    if explicit:
        return explicit
    legend_code = (data.get('legend_code') or '').strip().upper()
    if legend_code in LEGEND_CODE_TO_INTERACTION:
        return LEGEND_CODE_TO_INTERACTION[legend_code]
    if legend_code.startswith('X'):
        return 'OTHER NON-COLLISION'
    source = (data.get('interaction_source') or '').strip().upper()
    target = (data.get('interaction_target') or '').strip().upper()
    if source and target:
        return f'{source} TO {target}'
    return 'UNSPECIFIED'


def _incident_analytics_payload(quarter_filter=''):
    template = FormTemplate.query.filter_by(form_number=10).first()
    if not template:
        return {
            'has_template': False,
            'rows': [],
            'available_quarters': [],
            'quarter_filter': quarter_filter,
            'quarter_totals': {},
            'legend_counts': {},
            'interaction_counts': {},
            'cause_counts': {},
            'impact_counts': {},
            'total_occurrences': 0,
            'kpis': {},
            'top_interactions': [],
            'top_causes': [],
        }

    submissions = FormSubmission.query.filter_by(form_template_id=template.id).order_by(FormSubmission.created_at.desc()).all()

    rows = []
    for s in submissions:
        data = s.data or {}
        occurrence_dt = _safe_date_from_submission(s)
        quarter = _quarter_label(occurrence_dt)
        impact_equipment = _is_checked(data.get('damage_equipment')) or _is_checked(data.get('damage_to_equipment'))
        impact_aircraft = _is_checked(data.get('damage_aircraft')) or _is_checked(data.get('damage_to_aircraft'))
        impact_property = _is_checked(data.get('damage_property')) or _is_checked(data.get('damage_to_property'))
        impact_personnel = _is_checked(data.get('harm_personnel')) or _is_checked(data.get('harm_to_personnel'))
        impact_passenger = _is_checked(data.get('harm_passenger')) or _is_checked(data.get('harm_to_passenger'))

        rows.append({
            'submission': s,
            'reference_number': s.reference_number or f'SUB-{s.id}',
            'occurrence_date': occurrence_dt,
            'quarter': quarter,
            'location': (data.get('location') or s.location_ref or '').strip(),
            'legend': _normalize_incident_legend(data.get('incident_legend') or data.get('incident_type')),
            'legend_code': (data.get('legend_code') or '').strip().upper(),
            'interaction': _normalize_interaction(data),
            'cause': _normalize_incident_cause(data.get('cause_category') or data.get('cause_or_factor')),
            'impact_equipment': impact_equipment,
            'impact_aircraft': impact_aircraft,
            'impact_property': impact_property,
            'impact_personnel': impact_personnel,
            'impact_passenger': impact_passenger,
            'description': (data.get('description') or '').strip(),
            'notes': (data.get('incident_notes') or data.get('observations') or '').strip(),
        })

    available_quarters = sorted({row['quarter'] for row in rows}, reverse=True)
    if not quarter_filter:
        quarter_filter = available_quarters[0] if available_quarters else _quarter_label(date.today())

    filtered = [row for row in rows if row['quarter'] == quarter_filter] if quarter_filter else list(rows)

    quarter_totals = Counter(row['quarter'] for row in rows)
    legend_counts = Counter(row['legend'] for row in filtered)
    interaction_counts = Counter(row['interaction'] for row in filtered)
    cause_counts = Counter(row['cause'] for row in filtered)

    impact_counts = {
        'Damage to Equipment': sum(1 for row in filtered if row['impact_equipment']),
        'Damage to Aircraft': sum(1 for row in filtered if row['impact_aircraft']),
        'Damage to Property': sum(1 for row in filtered if row['impact_property']),
        'Harm to Personnel': sum(1 for row in filtered if row['impact_personnel']),
        'Harm to Passenger': sum(1 for row in filtered if row['impact_passenger']),
    }

    total_occurrences = len(filtered)
    aircraft_damage_rate = round((impact_counts['Damage to Aircraft'] / total_occurrences) * 100, 1) if total_occurrences else 0
    personnel_harm_rate = round((impact_counts['Harm to Personnel'] / total_occurrences) * 100, 1) if total_occurrences else 0

    return {
        'has_template': True,
        'rows': filtered,
        'available_quarters': available_quarters,
        'quarter_filter': quarter_filter,
        'quarter_totals': dict(sorted(quarter_totals.items())),
        'legend_counts': dict(legend_counts.most_common()),
        'interaction_counts': dict(interaction_counts.most_common()),
        'cause_counts': dict(cause_counts.most_common()),
        'impact_counts': impact_counts,
        'total_occurrences': total_occurrences,
        'kpis': {
            'Total Incidents (Quarter)': total_occurrences,
            'Aircraft Damage Rate %': aircraft_damage_rate,
            'Personnel Harm Rate %': personnel_harm_rate,
            'Top Cause': cause_counts.most_common(1)[0][0] if cause_counts else 'N/A',
        },
        'top_interactions': interaction_counts.most_common(12),
        'top_causes': cause_counts.most_common(12),
    }


def _normalize_sticker_status(value):
    raw = (value or '').strip().upper()
    if raw in ('GREEN', 'SERVICEABLE', 'COMPLIANT'):
        return 'GREEN'
    if raw in ('YELLOW', 'ORANGE', 'CONDITIONAL', 'GRACE'):
        return 'YELLOW'
    if raw in ('RED', 'GROUNDED', 'NON-COMPLIANT'):
        return 'RED'
    return ''


def _safe_submission_datetime(submission):
    data = submission.data or {}
    inspection_date = data.get('inspection_date')
    inspection_time = data.get('inspection_time')
    if inspection_date and inspection_time:
        try:
            return datetime.fromisoformat(f'{inspection_date}T{inspection_time}')
        except ValueError:
            pass
    if submission.submission_date and submission.submission_time:
        return datetime.combine(submission.submission_date, submission.submission_time)
    return submission.created_at


def _build_essat_sticker_rows(submissions):
    rows = []
    for submission in submissions:
        data = submission.data or {}
        sticker_status = _normalize_sticker_status(data.get('sticker_status'))
        rows.append({
            'submission': submission,
            'reference_number': submission.reference_number or f'SUB-{submission.id}',
            'company': (data.get('organization_company') or 'Unspecified').strip() or 'Unspecified',
            'vehicle_no': (data.get('airside_vehicle_no') or '').strip(),
            'equipment_description': (data.get('vehicle_equipment_description') or '').strip(),
            'sticker_no': (data.get('sticker_no') or '').strip(),
            'sticker_status': sticker_status,
            'serviceability_label': 'Serviceable' if sticker_status == 'GREEN' else 'Conditional (Grace)' if sticker_status == 'YELLOW' else 'Grounded' if sticker_status == 'RED' else 'Unknown',
            'inspection_date': data.get('inspection_date') or '',
            'inspection_time': data.get('inspection_time') or '',
            'submitted_at': _safe_submission_datetime(submission),
        })
    return rows


@report_bp.route('/daily-ops-report', methods=['GET', 'POST'])
@login_required
def daily_ops_report():
    if request.method == 'POST':
        # Uses Form 12 template submission storage
        from app import db
        template = FormTemplate.query.filter_by(form_number=12).first()
        if template:
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref='Airside Ops',
                data=request.form.to_dict(flat=False),
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)
            db.session.commit()
            flash('Daily operational report submitted.', 'success')
        return redirect(url_for('report.daily_ops_report'))

    reports = FormSubmission.query.join(FormTemplate).filter(
        FormTemplate.form_number == 12
    ).order_by(FormSubmission.created_at.desc()).limit(30).all()
    return render_template('reports/daily_ops_report.html', reports=reports)


@report_bp.route('/weekly-airside-report', methods=['GET', 'POST'])
@login_required
def weekly_airside_report():
    anchor_date = _parse_date(request.values.get('week_start') or request.values.get('date'))
    template, template_created = _ensure_weekly_airside_form_template()
    payload = _weekly_airside_payload(anchor_date)

    if request.method == 'POST':
        report = FormSubmission(
            form_template_id=template.id,
            status='submitted',
            submitted_by_user_id=current_user.id,
            location_ref='Airside Ops',
            submission_date=payload['week_end'],
            data={
                'week_start': payload['week_start'].isoformat(),
                'week_end': payload['week_end'].isoformat(),
                'pax_arriving_total': payload['week_pob_arrivals'],
                'pax_departing_total': payload['week_pob_departures'],
                'pax_total': payload['week_pob_total'],
                'incident_count': payload['incident_count'],
                'week_flight_total': payload['week_total'],
                'week_arrivals': payload['week_arrivals'],
                'week_departures': payload['week_departures'],
                'week_pob_arrivals': payload['week_pob_arrivals'],
                'week_pob_departures': payload['week_pob_departures'],
                'week_pob_total': payload['week_pob_total'],
                'phase_counts': payload['phase_counts'],
                'daily_rows': [
                    {
                        'date': row['date'].isoformat(),
                        'arrivals': row['arrivals'],
                        'departures': row['departures'],
                        'total': row['total'],
                        'pob_arrivals': row['pob_arrivals'],
                        'pob_departures': row['pob_departures'],
                        'pob_total': row['pob_total'],
                    }
                    for row in payload['daily_rows']
                ],
                'activity_total': payload['activity_total'],
                'top_forms': payload['top_forms'],
                'handover_rows': payload['handover_rows'],
                'violation_rows': payload['violation_rows'],
                'inspection_rows': payload['inspection_rows'],
                'tpbb_issue_rows': payload['tpbb_issue_rows'],
                'works_rows': payload['works_rows'],
                'activities_summary': request.form.get('activities_summary', '').strip(),
                'incident_summary': request.form.get('incident_summary', '').strip(),
                'remarks': request.form.get('remarks', '').strip(),
            },
        )
        db.session.add(report)
        WorkflowService.ensure_issue_for_submission(report, current_user)
        db.session.flush()
        report.generate_reference_number(prefix='WEEKLY')
        db.session.commit()
        flash('Weekly airside report saved.', 'success')
        if template_created:
            flash('Weekly Airside Report template was initialized automatically.', 'info')
        return redirect(url_for('report.weekly_airside_report', week_start=payload['week_start'].isoformat()))

    saved_reports = FormSubmission.query.join(FormTemplate).filter(
        FormTemplate.form_number == 26,
        FormSubmission.created_at >= datetime.combine(payload['week_start'], datetime.min.time()),
        FormSubmission.created_at < datetime.combine(payload['week_end'] + timedelta(days=1), datetime.min.time()),
    ).order_by(FormSubmission.created_at.desc()).all()

    return render_template(
        'reports/weekly_airside_report.html',
        template=template,
        saved_reports=saved_reports,
        saved_report_data=payload['latest_weekly_report'].data if payload['latest_weekly_report'] else {},
        selected_week=payload['week_start'],
        **payload,
    )


@report_bp.route('/analytics-dashboard')
@login_required
def analytics_dashboard():
    kpis = AnalyticsService.get_dashboard_kpis()
    trend = AnalyticsService.incident_trend(30)
    return render_template('reports/analytics_dashboard.html', kpis=kpis, trend=trend)


@report_bp.route('/custom-report-builder')
@login_required
def custom_report_builder():
    templates = FormTemplate.query.order_by(FormTemplate.form_number).all()
    return render_template('reports/custom_report_builder.html', templates=templates)


@report_bp.route('/essat-sticker-report')
@login_required
def essat_sticker_report():
    template = FormTemplate.query.filter_by(form_number=18).first()
    if not template:
        flash('ESSAT Motorised form template is not configured.', 'warning')
        return redirect(url_for('report.custom_report_builder'))

    registered_companies = Company.query.filter_by(is_active=True).order_by(Company.name).all()
    company_filter = (request.args.get('company') or '').strip()
    sticker_filter = _normalize_sticker_status(request.args.get('sticker_status') or 'GREEN') or 'GREEN'
    from_date = (request.args.get('from_date') or '').strip()
    to_date = (request.args.get('to_date') or '').strip()

    submissions = FormSubmission.query.filter_by(form_template_id=template.id).order_by(FormSubmission.created_at.desc()).all()
    rows = _build_essat_sticker_rows(submissions)

    if company_filter:
        rows = [row for row in rows if row['company'].lower() == company_filter.lower()]
    if sticker_filter:
        rows = [row for row in rows if row['sticker_status'] == sticker_filter]
    if from_date:
        rows = [row for row in rows if row['inspection_date'] and row['inspection_date'] >= from_date]
    if to_date:
        rows = [row for row in rows if row['inspection_date'] and row['inspection_date'] <= to_date]

    rows.sort(key=lambda row: (
        row['company'].lower(),
        row['inspection_date'] or '9999-12-31',
        row['inspection_time'] or '99:99',
        row['vehicle_no'].lower(),
    ))

    return render_template(
        'reports/essat_sticker_report.html',
        rows=rows,
        companies=registered_companies,
        company_filter=company_filter,
        sticker_filter=sticker_filter,
        from_date=from_date,
        to_date=to_date,
    )


@report_bp.route('/incident-analytics')
@login_required
def incident_analytics_report():
    quarter_filter = (request.args.get('quarter') or '').strip()
    payload = _incident_analytics_payload(quarter_filter=quarter_filter)
    if not payload['has_template']:
        flash('Incident report template (Form 10) is not configured.', 'warning')
        return redirect(url_for('report.custom_report_builder'))
    return render_template('reports/incident_analytics.html', **payload)


@report_bp.route('/incident-analytics/export.xlsx')
@login_required
def incident_analytics_export_excel():
    import pandas as pd

    quarter_filter = (request.args.get('quarter') or '').strip()
    payload = _incident_analytics_payload(quarter_filter=quarter_filter)

    summary_rows = [
        {'Metric': k, 'Value': v} for k, v in payload['kpis'].items()
    ]
    by_quarter_rows = [
        {'Quarter': q, 'Total Occurrences': total}
        for q, total in payload['quarter_totals'].items()
    ]
    by_cause_rows = [
        {'Cause': cause, 'Occurrences': count}
        for cause, count in payload['cause_counts'].items()
    ]
    by_interaction_rows = [
        {'Interaction Category': cat, 'Occurrences': count}
        for cat, count in payload['interaction_counts'].items()
    ]
    detailed_rows = [
        {
            'Reference': row['reference_number'],
            'Occurrence Date': row['occurrence_date'],
            'Quarter': row['quarter'],
            'Legend': row['legend'],
            'Legend Code': row.get('legend_code', ''),
            'Interaction': row['interaction'],
            'Cause': row['cause'],
            'Location': row['location'],
            'Damage Equipment': row['impact_equipment'],
            'Damage Aircraft': row['impact_aircraft'],
            'Damage Property': row['impact_property'],
            'Harm Personnel': row['impact_personnel'],
            'Harm Passenger': row['impact_passenger'],
            'Description': row['description'],
            'Notes': row['notes'],
        }
        for row in payload['rows']
    ]

    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        pd.DataFrame(summary_rows).to_excel(writer, index=False, sheet_name='Summary')
        pd.DataFrame(by_quarter_rows).to_excel(writer, index=False, sheet_name='By Quarter')
        pd.DataFrame(by_cause_rows).to_excel(writer, index=False, sheet_name='By Cause')
        pd.DataFrame(by_interaction_rows).to_excel(writer, index=False, sheet_name='By Interaction')
        pd.DataFrame(detailed_rows).to_excel(writer, index=False, sheet_name='Detailed Records')
    output.seek(0)

    return send_file(
        output,
        as_attachment=True,
        download_name=f'incident_analytics_{payload["quarter_filter"]}_{date.today().isoformat()}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
    )


@report_bp.route('/incident-analytics/export.pdf')
@login_required
def incident_analytics_export_pdf():
    quarter_filter = (request.args.get('quarter') or '').strip()
    payload = _incident_analytics_payload(quarter_filter=quarter_filter)
    service = PDFGeneratorService()

    summary_lines = []
    for cause, count in payload['top_causes'][:5]:
        summary_lines.append(f'Top Cause: {cause} ({count})')
    for category, count in payload['top_interactions'][:5]:
        summary_lines.append(f'Interaction: {category} ({count})')
    for impact, count in payload['impact_counts'].items():
        summary_lines.append(f'{impact}: {count}')

    pdf_bytes = service.generate_dashboard_report_pdf(
        title=f'Incident Analytics Report - {payload["quarter_filter"]}',
        kpis=payload['kpis'],
        charts_summary=summary_lines,
    )
    return send_file(
        BytesIO(pdf_bytes),
        as_attachment=True,
        download_name=f'incident_analytics_{payload["quarter_filter"]}_{date.today().isoformat()}.pdf',
        mimetype='application/pdf',
    )


@report_bp.route('/export/submissions.csv')
@login_required
def export_submissions_csv():
    submissions = FormSubmission.query.order_by(FormSubmission.created_at.desc()).all()
    df = ExportService.submissions_to_dataframe(submissions)
    csv_bytes = ExportService.to_csv_bytes(df)
    return Response(
        csv_bytes,
        mimetype='text/csv',
        headers={'Content-Disposition': f'attachment; filename=submissions_{date.today().isoformat()}.csv'}
    )


@report_bp.route('/export/submissions.xlsx')
@login_required
def export_submissions_excel():
    submissions = FormSubmission.query.order_by(FormSubmission.created_at.desc()).all()
    df = ExportService.submissions_to_dataframe(submissions)
    excel_bytes = ExportService.to_excel_bytes(df, sheet_name='Submissions')
    return send_file(
        BytesIO(excel_bytes),
        as_attachment=True,
        download_name=f'submissions_{date.today().isoformat()}.xlsx',
        mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    )


@report_bp.route('/submission/<int:submission_id>/pdf')
@login_required
def submission_pdf(submission_id):
    submission = FormSubmission.query.get_or_404(submission_id)
    service = PDFGeneratorService()
    title = submission.template.title if submission.template else 'Airside Form'
    pdf_bytes = service.generate_form_pdf(submission, template_title=title)
    filename = f"{submission.reference_number or f'SUB-{submission.id}'}.pdf"
    return send_file(
        BytesIO(pdf_bytes),
        as_attachment=True,
        download_name=filename,
        mimetype='application/pdf',
    )
