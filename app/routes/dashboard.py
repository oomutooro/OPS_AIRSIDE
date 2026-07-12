"""Dashboard routes and API endpoints for widgets/charts."""
from datetime import date, datetime, timedelta
from math import ceil
from collections import Counter, defaultdict
from flask import Blueprint, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app import db
from app.models.form import FormSubmission, FormTemplate, IssueWorkflow
from app.models.apron import Shift
from app.models.reference import ParkingStand
from app.models.flight import FlightMovement
from app.services.analytics_service import AnalyticsService
from app.services.workflow_service import WorkflowService
from app.services.aodb_sync import AodbSyncService


dashboard_bp = Blueprint('dashboard', __name__)

MANAGER_ROLES = {'admin', 'supervisor', 'auditor'}
SIZE_ORDER = {'A': 1, 'B': 2, 'C': 3, 'E': 4, 'F': 5}
NON_BRIDGE_TYPE_PREFIXES = (
    'AT4', 'AT5', 'AT6', 'AT7', 'DH8', 'DHC', 'SF3', 'BE1', 'PA2', 'PA3', 'C208', 'PC12', 'TBM', 'AN2', 'AN4'
)


def _parse_iso_date(value: str, fallback: date = None) -> date:
    raw = (value or '').strip()
    if raw:
        try:
            return datetime.strptime(raw, '%Y-%m-%d').date()
        except ValueError:
            pass
    return fallback or date.today()


def _effective_dt(flight: FlightMovement):
    return flight.actual_datetime or flight.estimated_datetime or flight.scheduled_datetime


def _normalize_stand_code(raw: str) -> str:
    stand = (raw or '').strip().upper().replace(' ', '')
    if (stand.startswith('A1S') or stand.startswith('A01S')) and len(stand) >= 5:
        stand = stand[-2:]
    if stand.startswith('S') and stand[1:].isdigit():
        stand = stand[1:].zfill(2)
    elif stand.isdigit():
        stand = stand.zfill(2)
    return stand


def _is_tpbb_stand(raw: str) -> bool:
    normalized = _normalize_stand_code(raw)
    return normalized in {'05', '06'}


def _tpbb_bridge_no(raw: str) -> str:
    normalized = _normalize_stand_code(raw)
    if normalized == '05':
        return 'PBB 01'
    if normalized == '06':
        return 'PBB 02'
    return ''


def _is_bridge_capable_type(actype: str) -> bool:
    if not actype:
        return True
    t = actype.upper().strip()
    return not any(t.startswith(prefix) for prefix in NON_BRIDGE_TYPE_PREFIXES)


def _stand_serviceable_for_bridge(raw_stand: str) -> bool:
    normalized = _normalize_stand_code(raw_stand)
    if normalized == '05':
        code = 'A1S05'
    elif normalized == '06':
        code = 'A1S06'
    else:
        return False

    stand = ParkingStand.query.filter_by(stand_code=code).first()
    if not stand:
        return True  # treat unknown as serviceable to avoid hiding gaps
    return bool(stand.is_active and stand.has_pbb)


def _flight_aliases(flight: FlightMovement):
    base = (flight.flight_number or '').replace(' ', '').upper()
    iata = f"{(flight.flight_iata_code or '').strip()}{(flight.flight_number or '').strip()}".replace(' ', '').upper()
    icao = f"{(flight.flight_icao_code or '').strip()}{(flight.flight_number or '').strip()}".replace(' ', '').upper()
    return {a for a in {base, iata, icao} if a}


def _manual_tpbb_map(for_date: date):
    rows = FormSubmission.query.join(FormTemplate).filter(FormTemplate.form_number == 5).all()
    result = {}
    for sub in rows:
        data = sub.data or {}
        rec_date = (data.get('tpbb_date') or '').strip()
        matched = False
        if rec_date:
            try:
                matched = datetime.strptime(rec_date, '%Y-%m-%d').date() == for_date
            except ValueError:
                matched = False
        else:
            matched = bool(sub.created_at and sub.created_at.date() == for_date)
        if not matched:
            continue

        key = (data.get('flight_number') or '').replace(' ', '').upper()
        if not key:
            continue
        result[key] = {
            'docking': bool((data.get('docking_time') or '').strip()),
            'backoff': bool((data.get('backoff_time') or '').strip()),
        }
    return result


def _size_code_from_type(actype: str) -> str:
    t = (actype or '').upper().strip()
    if not t:
        return 'C'
    if t.startswith(('A38',)):
        return 'F'
    if t.startswith(('B77', 'B78', 'A33', 'A34', 'A35', 'B74', 'B76', 'A31')):
        return 'E'
    if t.startswith(('AT', 'DH', 'DHC', 'C20', 'PC', 'BE', 'PA')):
        return 'B'
    return 'C'


def _movement_type(raw_payload: dict) -> str:
    return (raw_payload or {}).get('movementType', '') or ''


def _scope_window(selected_date: date, scope: str):
    if scope == 'week':
        start = selected_date - timedelta(days=selected_date.weekday())
        end = start + timedelta(days=6)
        return start, end
    if scope == 'month':
        start = selected_date.replace(day=1)
        if selected_date.month == 12:
            nxt = date(selected_date.year + 1, 1, 1)
        else:
            nxt = date(selected_date.year, selected_date.month + 1, 1)
        return start, nxt - timedelta(days=1)
    return selected_date, selected_date


def _daterange(start_date: date, end_date: date):
    d = start_date
    while d <= end_date:
        yield d
        d += timedelta(days=1)


def _dashboard_payload(selected_date: date, scope: str):
    start_date, end_date = _scope_window(selected_date, scope)
    start_key = start_date.strftime('%Y%m%d')
    end_key = end_date.strftime('%Y%m%d')

    flights = FlightMovement.query.filter(
        FlightMovement.scheduled_date >= start_key,
        FlightMovement.scheduled_date <= end_key,
    ).order_by(FlightMovement.scheduled_datetime.asc()).all()

    day_flights_all = [f for f in flights if f.scheduled_date == selected_date.strftime('%Y%m%d')]

    # Schedule list rule: for today show from now-2h onward; otherwise full day list.
    if selected_date == date.today():
        threshold = datetime.now() - timedelta(hours=2)
        day_flights_for_list = [f for f in day_flights_all if (_effective_dt(f) or datetime.min) >= threshold]
    else:
        day_flights_for_list = list(day_flights_all)

    stand_pending_count = sum(1 for f in day_flights_all if not (f.stand or '').strip())

    manual_tpbb = _manual_tpbb_map(selected_date)
    tpbb_total = 0
    tpbb_complete = 0
    tpbb_incomplete = 0
    tpbb_unserviceable = 0
    incomplete_rows = []

    for f in day_flights_all:
        if not _is_tpbb_stand(f.stand):
            continue
        tpbb_total += 1
        serviceable = _stand_serviceable_for_bridge(f.stand)
        if not serviceable:
            tpbb_unserviceable += 1
            continue

        aliases = _flight_aliases(f)
        manual = None
        for key in aliases:
            if key in manual_tpbb:
                manual = manual_tpbb[key]
                break

        dock_ok = bool(f.milestone_3) or bool(manual and manual.get('docking'))
        backoff_ok = bool(f.milestone_1) or bool(manual and manual.get('backoff'))
        primary_ok = dock_ok if (f.arr_or_dep or '').upper() == 'ARR' else backoff_ok

        if primary_ok:
            tpbb_complete += 1
        else:
            tpbb_incomplete += 1
            raw = f.raw_payload or {}
            aircraft_type = (raw.get('acType') or raw.get('aircraftType') or '').strip()
            incomplete_rows.append({
                'flight': f"{(f.flight_icao_code or '').strip()}{(f.flight_number or '').strip()}".strip() or (f.flight_number or '-'),
                'arr_or_dep': f.arr_or_dep,
                'bridge': _tpbb_bridge_no(f.stand),
                'stand': f.stand or '-',
                'aircraft_type': aircraft_type or '-',
                'status': f.operation_status or '-',
            })

    # Arrivals/departures chart by day across selected scope
    day_labels = []
    arr_values = []
    dep_values = []
    for d in _daterange(start_date, end_date):
        key = d.strftime('%Y%m%d')
        subset = [f for f in flights if f.scheduled_date == key]
        day_labels.append(d.strftime('%d %b'))
        arr_values.append(sum(1 for f in subset if (f.arr_or_dep or '').upper() == 'ARR'))
        dep_values.append(sum(1 for f in subset if (f.arr_or_dep or '').upper() == 'DEP'))

    # Timing/peak chart by hour for selected date
    hourly = [0] * 24
    for f in day_flights_all:
        dt = _effective_dt(f)
        if dt:
            hourly[dt.hour] += 1
    peak_hour = max(range(24), key=lambda h: hourly[h]) if day_flights_all else 0

    # POB by aircraft type (selected scope)
    pob_range = AodbSyncService.pob_stats_for_range(start_date, end_date)
    pob_token_by_day = {}
    for daily in pob_range['daily']:
        d = daily['date'].strftime('%Y%m%d')
        token_map = {}
        for row in daily['rows']:
            token = (row.get('flight_key') or '').upper()
            if token:
                token_map[token] = row.get('pob') or 0
        pob_token_by_day[d] = token_map

    aircraft_expected = Counter()
    aircraft_operated = Counter()
    aircraft_pob = defaultdict(int)
    aircraft_pob_samples = defaultdict(int)

    scheduled_count = 0
    non_scheduled_count = 0
    for f in flights:
        raw = f.raw_payload or {}
        actype = (raw.get('acType') or raw.get('aircraftType') or '').strip().upper() or 'UNKNOWN'
        aircraft_expected[actype] += 1
        if f.actual_datetime:
            aircraft_operated[actype] += 1

        service_type = (raw.get('flightServiceType') or '').strip().upper()
        movement_type = _movement_type(raw).lower()
        if service_type == 'J' or 'scheduled' in movement_type:
            scheduled_count += 1
        else:
            non_scheduled_count += 1

        aliases = _flight_aliases(f)
        day_token_map = pob_token_by_day.get(f.scheduled_date or '', {})
        pob_val = None
        for token in aliases:
            if token in day_token_map:
                pob_val = day_token_map[token]
                break
        if pob_val is not None:
            aircraft_pob[actype] += pob_val
            aircraft_pob_samples[actype] += 1

    aircraft_type_rows = []
    for actype, expected in aircraft_expected.most_common(12):
        operated = aircraft_operated.get(actype, 0)
        pob_total = aircraft_pob.get(actype, 0)
        samples = aircraft_pob_samples.get(actype, 0)
        expected_pob = round(pob_total / samples, 1) if samples else 0
        aircraft_type_rows.append({
            'type': actype,
            'expected': expected,
            'operated': operated,
            'pob_expected': expected_pob,
            'pob_total': pob_total,
        })

    # Stand suggestions for unallocated flights (selected day)
    active_stands = ParkingStand.query.filter_by(is_active=True).order_by(ParkingStand.stand_code.asc()).all()
    occupied = {_normalize_stand_code(f.stand) for f in day_flights_all if (f.stand or '').strip()}
    stand_suggestions = []
    for f in day_flights_all:
        if (f.stand or '').strip():
            continue
        raw = f.raw_payload or {}
        actype = (raw.get('acType') or raw.get('aircraftType') or '').strip().upper()
        size_code = _size_code_from_type(actype)
        min_size = SIZE_ORDER.get(size_code, 3)
        bridge_pref = _is_bridge_capable_type(actype)
        candidates = []
        for s in active_stands:
            norm = _normalize_stand_code(s.stand_code)
            if norm in occupied:
                continue
            stand_size = SIZE_ORDER.get((s.category or 'C').upper(), 3)
            if stand_size < min_size:
                continue
            if bridge_pref and s.has_pbb:
                score = 0
            elif bridge_pref:
                score = 2
            else:
                score = 1
            candidates.append((score, s.stand_code))
        candidates.sort(key=lambda x: (x[0], x[1]))
        top = [c[1] for c in candidates[:3]]
        stand_suggestions.append({
            'flight': f"{(f.flight_icao_code or '').strip()}{(f.flight_number or '').strip()}".strip() or (f.flight_number or '-'),
            'aircraft_type': actype or '-',
            'size_code': size_code,
            'suggestions': top,
        })

    return {
        'start_date': start_date,
        'end_date': end_date,
        'flights_scope_count': len(flights),
        'day_flights_count': len(day_flights_all),
        'stand_pending_count': stand_pending_count,
        'tpbb_total': tpbb_total,
        'tpbb_complete': tpbb_complete,
        'tpbb_incomplete': tpbb_incomplete,
        'tpbb_unserviceable': tpbb_unserviceable,
        'incomplete_rows': incomplete_rows[:30],
        'arr_dep_chart': {
            'labels': day_labels,
            'arrivals': arr_values,
            'departures': dep_values,
        },
        'hourly_chart': {
            'labels': [f'{h:02d}:00' for h in range(24)],
            'values': hourly,
            'peak_hour': f'{peak_hour:02d}:00',
            'peak_volume': hourly[peak_hour] if hourly else 0,
        },
        'scheduled_count': scheduled_count,
        'non_scheduled_count': non_scheduled_count,
        'aircraft_type_rows': aircraft_type_rows,
        'stand_suggestions': stand_suggestions[:20],
        'day_flights_for_list': day_flights_for_list,
    }


@dashboard_bp.route('/')
@login_required
def index():
    selected_date = _parse_iso_date(request.args.get('date'))
    requested_scope = (request.args.get('scope') or 'day').lower()
    is_manager = current_user.role in MANAGER_ROLES
    scope = requested_scope if is_manager and requested_scope in {'day', 'week', 'month'} else 'day'

    payload = _dashboard_payload(selected_date, scope)
    kpis = AnalyticsService.get_dashboard_kpis()
    recent_submissions = FormSubmission.query.order_by(FormSubmission.created_at.desc()).limit(20).all()
    current_shift = Shift.query.filter_by(status='active').order_by(Shift.created_at.desc()).first()
    workflow_data = WorkflowService.dashboard_data_for_user(current_user)
    last_sync = AodbSyncService.last_sync_time()

    page = max(1, request.args.get('flight_page', type=int) or 1)
    per_page = 20
    schedule_rows = payload['day_flights_for_list']
    total_rows = len(schedule_rows)
    total_pages = max(1, ceil(total_rows / per_page))
    page = min(page, total_pages)
    start = (page - 1) * per_page
    end = start + per_page
    schedule_page_rows = schedule_rows[start:end]

    dashboard_json = {
        'arrDep': payload['arr_dep_chart'],
        'hourly': payload['hourly_chart'],
    }

    return render_template(
        'dashboard.html',
        selected_date=selected_date,
        scope=scope,
        is_manager=is_manager,
        kpis=kpis,
        recent_submissions=recent_submissions,
        current_shift=current_shift,
        pending_directed=workflow_data['pending_directed'],
        closed_recent=workflow_data['closed_recent'],
        workflow_stats=workflow_data['workflow_stats'],
        role_breakdown=workflow_data['role_breakdown'],
        department_overview=workflow_data['department_overview'],
        flights_scope_count=payload['flights_scope_count'],
        day_flights_count=payload['day_flights_count'],
        stand_pending_count=payload['stand_pending_count'],
        tpbb_total=payload['tpbb_total'],
        tpbb_complete=payload['tpbb_complete'],
        tpbb_incomplete=payload['tpbb_incomplete'],
        tpbb_unserviceable=payload['tpbb_unserviceable'],
        incomplete_rows=payload['incomplete_rows'],
        scheduled_count=payload['scheduled_count'],
        non_scheduled_count=payload['non_scheduled_count'],
        aircraft_type_rows=payload['aircraft_type_rows'],
        stand_suggestions=payload['stand_suggestions'],
        schedule_rows=schedule_page_rows,
        flight_page=page,
        flight_total_pages=total_pages,
        flight_total_rows=total_rows,
        dashboard_payload=dashboard_json,
        last_sync=last_sync,
    )


@dashboard_bp.route('/workflow/<int:issue_id>/advance', methods=['POST'])
@login_required
def advance_issue(issue_id):
    issue = db.session.get(IssueWorkflow, issue_id)
    if not issue:
        flash('Issue workflow item was not found.', 'danger')
        return redirect(url_for('dashboard.index'))

    note = (request.form.get('note') or '').strip()
    ok, message = issue.advance(current_user, note)
    if ok:
        db.session.commit()
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/workflow/<int:issue_id>/close', methods=['POST'])
@login_required
def close_issue(issue_id):
    issue = db.session.get(IssueWorkflow, issue_id)
    if not issue:
        flash('Issue workflow item was not found.', 'danger')
        return redirect(url_for('dashboard.index'))

    note = (request.form.get('closure_notes') or '').strip()
    ok, message = issue.close(current_user, note)
    if ok:
        if issue.submission and issue.submission.status != 'closed':
            issue.submission.status = 'closed'
        db.session.commit()
        flash(message, 'success')
    else:
        flash(message, 'danger')
    return redirect(url_for('dashboard.index'))


@dashboard_bp.route('/api/kpis')
@login_required
def api_kpis():
    return jsonify(AnalyticsService.get_dashboard_kpis())


@dashboard_bp.route('/api/incident-trend')
@login_required
def api_incident_trend():
    return jsonify(AnalyticsService.incident_trend(7))
