"""
Apron management routes: stand allocation, shift handover, staff deployment, TPBB ops.
"""
from datetime import date, datetime, timedelta
from flask import Blueprint, current_app, flash, jsonify, redirect, render_template, request, url_for
from flask_login import current_user, login_required
from app import db
from app.models.apron import StandAllocation, Shift, ShiftRoster, HandoverReport
from app.models.reference import ParkingStand
from app.models.user import User
from app.models.form import FormSubmission, FormTemplate
from app.models.flight import FlightMovement
from app.services.workflow_service import WorkflowService
from app.services.aodb_sync import AodbSyncService
from app.utils.decorators import role_required

apron_bp = Blueprint('apron', __name__)


def _parse_iso_date(value: str, default_value: date = None) -> date:
    if not value:
        return default_value or date.today()
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except ValueError:
        return default_value or date.today()


def _normalize_stand_code(raw: str) -> str:
    """Normalize stand code from AODB/system values to map stand IDs (02..10, 20..25)."""
    if not raw:
        return ''
    stand = str(raw).strip().upper().replace(' ', '')
    if stand.startswith('A1S') and len(stand) >= 5:
        return stand[-2:]
    if stand.startswith('S') and len(stand) >= 3 and stand[1:].isdigit():
        return stand[1:].zfill(2)
    if stand.isdigit():
        return stand.zfill(2)
    return stand


def _valid_map_stands():
    return {'02', '03', '04', '05', '06', '07', '08', '09', '10', '20', '21', '22', '23', '24', '25'}


def _user_is_on_shift(user_id: int, duty_date: date, shift_type: str) -> bool:
    entry = ShiftRoster.query.filter_by(user_id=user_id, duty_date=duty_date).first()
    if not entry:
        return False
    return entry.duty_type == shift_type


def _on_duty_users(duty_date: date, shift_type: str):
    return db.session.query(User).join(ShiftRoster, ShiftRoster.user_id == User.id).filter(
        ShiftRoster.duty_date == duty_date,
        ShiftRoster.duty_type == shift_type,
        User.is_active.is_(True),
        User.role == 'operator',
    ).order_by(User.full_name).all()


def _eligible_roster_users():
    """Default roster pool used for auto generation (operators only)."""
    return User.query.filter(
        User.is_active.is_(True),
        User.role == 'operator'
    ).order_by(User.full_name).all()


def _build_shift_members(duty_date: date, shift_type: str):
    members = []
    entries = ShiftRoster.query.filter_by(duty_date=duty_date, duty_type=shift_type).all()
    for entry in entries:
        if not entry.user:
            continue
        members.append({
            'user_id': entry.user.id,
            'name': entry.user.full_name,
            'badge': entry.user.badge_number,
            'role': entry.user.role,
            'station': None,
        })
    return members


def _choose_shift_leader(member_user_ids, preferred_leader_ids):
    for uid in preferred_leader_ids:
        if uid in member_user_ids:
            return uid
    return member_user_ids[0] if member_user_ids else None


def _resolve_fixed_shift_leaders(preferred_leader_ids):
    """Resolve month-fixed shift leaders from selected users: first=day, second=night."""
    day_leader_id = preferred_leader_ids[0] if preferred_leader_ids else None
    night_leader_id = preferred_leader_ids[1] if len(preferred_leader_ids) > 1 else day_leader_id
    return {
        'day': day_leader_id,
        'night': night_leader_id,
    }


def _upsert_shift_records_for_range(start_date: date, end_date: date, preferred_leader_ids, fixed_leaders=None):
    """Create/update Shift records from rostered day/night entries."""
    fixed_leaders = fixed_leaders or {}
    days = (end_date - start_date).days + 1
    for offset in range(days):
        shift_date = start_date + timedelta(days=offset)
        for shift_type in ('day', 'night'):
            members = _build_shift_members(shift_date, shift_type)
            member_user_ids = [m['user_id'] for m in members if m.get('user_id')]
            fixed_leader_id = fixed_leaders.get(shift_type)
            leader_user_id = fixed_leader_id if fixed_leader_id else _choose_shift_leader(member_user_ids, preferred_leader_ids)
            leader = db.session.get(User, leader_user_id) if leader_user_id else None

            record = Shift.query.filter_by(shift_date=shift_date, shift_type=shift_type).first()
            if not record:
                record = Shift(
                    shift_date=shift_date,
                    shift_type=shift_type,
                    status='active',
                )
                db.session.add(record)

            record.members = members
            record.attending_count = len(members)
            record.leader_user_id = leader_user_id
            record.leader_name = leader.full_name if leader else None


@apron_bp.route('/stand-allocation', methods=['GET', 'POST'])
@role_required('admin', 'supervisor', 'inspector', 'operator')
def stand_allocation():
    if request.method == 'POST':
        allocation = StandAllocation(
            allocation_date=date.today(),
            flight_number=request.form.get('flight_number'),
            aircraft_registration=request.form.get('aircraft_registration'),
            aircraft_type=request.form.get('aircraft_type'),
            allocated_stand_code=request.form.get('allocated_stand'),
            requested_stand_code=request.form.get('requested_stand'),
            requires_follow_me=bool(request.form.get('requires_follow_me')),
            flight_type=request.form.get('flight_type'),
            status='allocated',
            allocated_by_user_id=current_user.id,
        )
        db.session.add(allocation)
        db.session.commit()
        flash('Stand allocation saved.', 'success')
        return redirect(url_for('apron.stand_allocation'))

    stands = ParkingStand.query.filter_by(is_active=True).order_by(ParkingStand.stand_code).all()
    allocations = StandAllocation.query.order_by(StandAllocation.created_at.desc()).limit(20).all()
    alloc_date = _parse_iso_date(request.args.get('date'))
    aodb_flights = AodbSyncService.flights_for_date(alloc_date)
    last_sync = AodbSyncService.last_sync_time()
    return render_template(
        'apron/stand_allocation.html',
        stands=stands,
        allocations=allocations,
        aodb_flights=aodb_flights,
        alloc_date=alloc_date,
        last_sync=last_sync,
        timedelta=timedelta,
    )


# ---------------------------------------------------------------------------
# AODB Sync management  (admin/supervisor/operator)
# ---------------------------------------------------------------------------

@apron_bp.route('/aodb-sync', methods=['GET', 'POST'])
@role_required('admin', 'supervisor', 'operator')
def aodb_sync():
    """Manual AODB flight data sync page."""
    sync_result = None
    selected_date = _parse_iso_date(request.args.get('date', date.today().isoformat()))

    if request.method == 'POST':
        raw_date = request.form.get('sync_date', date.today().isoformat())
        selected_date = _parse_iso_date(raw_date)
        sync_result = AodbSyncService.sync_date(selected_date)
        if sync_result['errors']:
            flash(f"Sync completed with errors: {'; '.join(sync_result['errors'])}", 'warning')
        else:
            flash(
                f"Sync OK \u2014 {sync_result['arrivals']} arrivals, "
                f"{sync_result['departures']} departures, "
                f"{sync_result['upserted']} records upserted.",
                'success',
            )

    last_sync = AodbSyncService.last_sync_time()
    recent = AodbSyncService.flights_for_date(selected_date)
    return render_template(
        'apron/aodb_sync.html',
        sync_result=sync_result,
        last_sync=last_sync,
        recent=recent,
        selected_date=selected_date.isoformat(),
        is_mock_mode=bool(current_app.config.get('AODB_MOCK_MODE', False)),
    )


# ---------------------------------------------------------------------------
# AODB Flights JSON API  (used by form dropdowns)
# ---------------------------------------------------------------------------

@apron_bp.route('/api/flights')
@login_required
def api_flights():
    """
    Return JSON list of flight numbers for a given date.
    Query params:
      date=YYYY-MM-DD  (defaults to today)
      type=arr|dep|all (defaults to all)
    """
    raw_date = request.args.get('date', date.today().isoformat())
    query_date = _parse_iso_date(raw_date)
    arr_or_dep = (request.args.get('type') or 'all').upper()
    if arr_or_dep == 'ALL':
        arr_or_dep = None
    flights = AodbSyncService.flights_for_date(query_date, arr_or_dep)
    return jsonify([f.to_dict() for f in flights])


@apron_bp.route('/stand-map')
@role_required('admin', 'supervisor', 'inspector', 'operator')
def stand_map():
    map_date = _parse_iso_date(request.args.get('date'))
    return render_template('apron/stand_map.html', map_date=map_date)


@apron_bp.route('/api/stand-map-data')
@role_required('admin', 'supervisor', 'inspector', 'operator')
def api_stand_map_data():
    """Merged stand-map feed from AODB flights and locally saved stand allocations."""
    query_date = _parse_iso_date(request.args.get('date', date.today().isoformat()))
    valid_stands = _valid_map_stands()

    # 1) AODB schedule view for selected date
    flights = AodbSyncService.flights_for_date(query_date)

    # 2) Local allocations created in this system for selected date
    allocations = StandAllocation.query.filter_by(allocation_date=query_date).order_by(StandAllocation.created_at.desc()).all()

    # Build merged planned entries by stand; prefer local allocation over AODB when both exist.
    planned_by_stand = {}
    flight_options = []

    for f in flights:
        stand_id = _normalize_stand_code(f.stand)
        if stand_id not in valid_stands:
            continue

        icao_num = f"{(f.flight_icao_code or '').strip()}{(f.flight_number or '').strip()}".strip()
        flight_label = icao_num or (f.flight_number or '').strip()
        if not flight_label:
            continue

        raw = f.raw_payload or {}
        aircraft_type = (raw.get('acType') or raw.get('aircraftType') or '').strip()
        sta_dt = f.estimated_datetime if f.arr_or_dep == 'ARR' and f.estimated_datetime else f.scheduled_datetime
        std_dt = f.scheduled_datetime

        planned_by_stand[stand_id] = {
            'stand_id': stand_id,
            'flight_number': flight_label,
            'aircraft_type': aircraft_type,
            'sta': sta_dt.strftime('%H:%M') if sta_dt else '',
            'std': std_dt.strftime('%H:%M') if std_dt else '',
            'source': 'aodb',
            'status': 'Planned',
        }

        flight_options.append({
            'flight_number': flight_label,
            'aircraft_type': aircraft_type,
            'stand_id': stand_id,
            'source': 'aodb',
        })

    for a in allocations:
        stand_id = _normalize_stand_code(a.allocated_stand_code or a.requested_stand_code)
        if stand_id not in valid_stands:
            continue
        flight_number = (a.flight_number or '').strip()
        if not flight_number:
            continue

        planned_by_stand[stand_id] = {
            'stand_id': stand_id,
            'flight_number': flight_number,
            'aircraft_type': (a.aircraft_type or '').strip(),
            'sta': a.eta.strftime('%H:%M') if a.eta else '',
            'std': a.etd.strftime('%H:%M') if a.etd else '',
            'source': 'system',
            'status': 'Planned',
        }

        flight_options.append({
            'flight_number': flight_number,
            'aircraft_type': (a.aircraft_type or '').strip(),
            'stand_id': stand_id,
            'source': 'system',
        })

    # Deduplicate flight options by flight+stand
    seen = set()
    unique_options = []
    for option in flight_options:
        key = (option['flight_number'], option['stand_id'])
        if key in seen:
            continue
        seen.add(key)
        unique_options.append(option)

    return jsonify({
        'date': query_date.isoformat(),
        'planned_assignments': list(planned_by_stand.values()),
        'flight_options': unique_options,
    })


@apron_bp.route('/shift-handover', methods=['GET', 'POST'])
@login_required
def shift_handover():
    handover_date = _parse_iso_date(request.form.get('handover_date') if request.method == 'POST' else request.args.get('handover_date'))

    if request.method == 'POST':
        signature_enabled = current_app.config.get('SIGNATURE_CAPTURE_ENABLED', False)
        outgoing_user_id = int(request.form.get('outgoing_user_id') or 0)
        incoming_user_id = int(request.form.get('incoming_user_id') or 0)
        outgoing_shift_type = (request.form.get('outgoing_shift_type') or 'day').lower()
        incoming_shift_type = (request.form.get('incoming_shift_type') or 'night').lower()

        outgoing_user = db.session.get(User, outgoing_user_id)
        incoming_user = db.session.get(User, incoming_user_id)

        if not outgoing_user or not incoming_user:
            flash('Please select valid outgoing and incoming shift personnel.', 'danger')
            return redirect(url_for('apron.shift_handover', handover_date=handover_date.isoformat()))

        if not _user_is_on_shift(outgoing_user.id, handover_date, outgoing_shift_type):
            flash(f'{outgoing_user.full_name} is not rostered for {outgoing_shift_type} shift on {handover_date}.', 'danger')
            return redirect(url_for('apron.shift_handover', handover_date=handover_date.isoformat()))

        if not _user_is_on_shift(incoming_user.id, handover_date, incoming_shift_type):
            flash(f'{incoming_user.full_name} is not rostered for {incoming_shift_type} shift on {handover_date}.', 'danger')
            return redirect(url_for('apron.shift_handover', handover_date=handover_date.isoformat()))

        report = HandoverReport(
            handover_date=handover_date,
            outgoing_name=outgoing_user.full_name,
            outgoing_badge=outgoing_user.badge_number,
            incoming_name=incoming_user.full_name,
            incoming_badge=incoming_user.badge_number,
            major_events=request.form.get('major_events'),
            pending_issues=request.form.get('pending_issues'),
            outgoing_sign=request.form.get('outgoing_signature') if signature_enabled else None,
            incoming_sign=request.form.get('incoming_signature') if signature_enabled else None,
            status='complete' if (not signature_enabled) or (request.form.get('outgoing_signature') and request.form.get('incoming_signature')) else 'pending',
        )
        db.session.add(report)

        template = FormTemplate.query.filter_by(form_number=2).first()
        if template:
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref='Apron Tower',
                data={
                    'recorded_by': current_user.full_name,
                    'handover_date': handover_date.isoformat(),
                    'outgoing_shift_type': outgoing_shift_type,
                    'incoming_shift_type': incoming_shift_type,
                    'outgoing_user_id': outgoing_user.id,
                    'incoming_user_id': incoming_user.id,
                    'outgoing_name': report.outgoing_name,
                    'incoming_name': report.incoming_name,
                    'major_events': report.major_events,
                    'pending_issues': report.pending_issues,
                },
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)

        db.session.commit()
        flash('Shift handover report submitted.', 'success')
        return redirect(url_for('apron.shift_handover'))

    reports = HandoverReport.query.order_by(HandoverReport.created_at.desc()).limit(20).all()
    day_users = _on_duty_users(handover_date, 'day')
    night_users = _on_duty_users(handover_date, 'night')
    return render_template(
        'apron/shift_handover.html',
        reports=reports,
        handover_date=handover_date,
        day_users=day_users,
        night_users=night_users,
        signature_capture_enabled=bool(current_app.config.get('SIGNATURE_CAPTURE_ENABLED', False)),
    )


@apron_bp.route('/shift-roster', methods=['GET', 'POST'])
@role_required('admin', 'supervisor')
def shift_roster():
    if request.method == 'POST':
        action = (request.form.get('action') or 'generate').strip().lower()

        if action == 'availability':
            user_id = int(request.form.get('availability_user_id') or 0)
            start_date = _parse_iso_date(request.form.get('availability_start_date'))
            end_date = _parse_iso_date(request.form.get('availability_end_date'), start_date)
            availability_type = (request.form.get('availability_type') or '').strip().lower()
            availability_note = (request.form.get('availability_note') or '').strip()
            operator_ids = {u.id for u in _eligible_roster_users()}

            availability_duty_map = {
                'leave': 'leave',
                'study_leave': 'study_leave',
                'office_hours': 'office',
            }

            if user_id <= 0 or availability_type not in availability_duty_map or user_id not in operator_ids:
                flash('Please provide valid availability details.', 'danger')
                return redirect(url_for('apron.shift_roster'))

            if end_date < start_date:
                flash('Availability end date must be on or after start date.', 'danger')
                return redirect(url_for('apron.shift_roster'))

            duty_value = availability_duty_map[availability_type]
            days = (end_date - start_date).days + 1
            created_count = 0
            updated_count = 0

            for offset in range(days):
                duty_date = start_date + timedelta(days=offset)
                entry = ShiftRoster.query.filter_by(user_id=user_id, duty_date=duty_date).first()
                note_text = f'availability:{availability_type}' + (f' | {availability_note}' if availability_note else '')
                if entry:
                    entry.duty_type = duty_value
                    entry.cycle_day_index = 2
                    entry.notes = note_text
                    entry.created_by_user_id = current_user.id
                    updated_count += 1
                else:
                    db.session.add(ShiftRoster(
                        duty_date=duty_date,
                        user_id=user_id,
                        duty_type=duty_value,
                        cycle_day_index=2,
                        notes=note_text,
                        created_by_user_id=current_user.id,
                    ))
                    created_count += 1

            db.session.commit()
            flash(f'Availability saved: {created_count} created, {updated_count} updated.', 'success')
            return redirect(url_for('apron.shift_roster', date=start_date.isoformat()))

        start_date = _parse_iso_date(request.form.get('start_date'))
        end_date = _parse_iso_date(request.form.get('end_date'), start_date)
        auto_select_available = request.form.get('auto_select_available') == 'on'
        operator_ids = {u.id for u in _eligible_roster_users()}
        if auto_select_available:
            user_ids = sorted(operator_ids)
        else:
            user_ids = [int(uid) for uid in request.form.getlist('user_ids') if uid.isdigit() and int(uid) in operator_ids]

        leader_user_ids = [int(uid) for uid in request.form.getlist('leader_user_ids') if uid.isdigit() and int(uid) in operator_ids]
        start_cycle = (request.form.get('start_cycle') or 'day').lower()
        overwrite_existing = request.form.get('overwrite_existing') == 'on'

        if end_date < start_date:
            flash('End date must be on or after start date.', 'danger')
            return redirect(url_for('apron.shift_roster'))

        if not user_ids:
            flash('Please select at least one user for roster generation.', 'danger')
            return redirect(url_for('apron.shift_roster'))

        start_idx = ShiftRoster.index_for_duty(start_cycle)
        days = (end_date - start_date).days + 1
        created_count = 0
        updated_count = 0

        # Pre-load all existing leave/availability blocks in the period for quick lookup.
        # These are NEVER overwritten — leave dates are excluded from roster generation entirely.
        ordered_user_ids = sorted(set(user_ids))
        leave_date_set = set()
        leave_rows = ShiftRoster.query.filter(
            ShiftRoster.user_id.in_(ordered_user_ids),
            ShiftRoster.duty_date >= start_date,
            ShiftRoster.duty_date <= end_date,
            ShiftRoster.duty_type.in_(['leave', 'study_leave', 'office']),
        ).all()
        for lv in leave_rows:
            leave_date_set.add((lv.user_id, lv.duty_date))

        # Split selected personnel into 4 rotating cohorts so day/night/off/off are concurrent.
        for order_idx, user_id in enumerate(ordered_user_ids):
            cohort_offset = order_idx % 4
            for offset in range(days):
                duty_date = start_date + timedelta(days=offset)

                # Always skip dates where this user has a leave/availability block.
                if (user_id, duty_date) in leave_date_set:
                    continue

                cycle_idx = (start_idx + cohort_offset + offset) % 4
                duty_type = ShiftRoster.duty_for_index(cycle_idx)
                entry = ShiftRoster.query.filter_by(user_id=user_id, duty_date=duty_date).first()
                if entry:
                    if overwrite_existing:
                        entry.duty_type = duty_type
                        entry.cycle_day_index = cycle_idx
                        entry.created_by_user_id = current_user.id
                        entry.notes = None
                        updated_count += 1
                    # else: leave existing day/night/off entries untouched
                else:
                    db.session.add(ShiftRoster(
                        duty_date=duty_date,
                        user_id=user_id,
                        duty_type=duty_type,
                        cycle_day_index=cycle_idx,
                        created_by_user_id=current_user.id,
                    ))
                    created_count += 1

        fixed_leaders = _resolve_fixed_shift_leaders(leader_user_ids)
        _upsert_shift_records_for_range(start_date, end_date, leader_user_ids, fixed_leaders=fixed_leaders)
        db.session.commit()

        # Coverage check: warn for any date where day or night shift has fewer than 2 staff.
        low_coverage = []
        for offset in range(min(days, 62)):
            check_date = start_date + timedelta(days=offset)
            day_n = ShiftRoster.query.filter_by(duty_date=check_date, duty_type='day').count()
            night_n = ShiftRoster.query.filter_by(duty_date=check_date, duty_type='night').count()
            if day_n < 2 or night_n < 2:
                low_coverage.append(f"{check_date.strftime('%d %b')} (D:{day_n} N:{night_n})")
        if low_coverage:
            sample = ', '.join(low_coverage[:5])
            extra = f' +{len(low_coverage) - 5} more' if len(low_coverage) > 5 else ''
            flash(
                f'Low shift coverage on {len(low_coverage)} day(s): {sample}{extra}. '
                'Add more staff or adjust leave before this period.',
                'warning',
            )

        flash(f'Roster saved: {created_count} created, {updated_count} updated.', 'success')
        return redirect(url_for('apron.shift_roster'))

    target_date = _parse_iso_date(request.args.get('date'))
    users = User.query.filter(
        User.is_active.is_(True),
        User.role == 'operator'
    ).order_by(User.full_name).all()
    roster_entries = ShiftRoster.query.filter_by(duty_date=target_date).order_by(ShiftRoster.duty_type, ShiftRoster.user_id).all()
    availability_entries = ShiftRoster.query.filter(
        ShiftRoster.duty_date >= target_date,
        ShiftRoster.duty_date <= (target_date + timedelta(days=30)),
        ShiftRoster.duty_type.in_(['leave', 'study_leave', 'office'])
    ).order_by(ShiftRoster.duty_date, ShiftRoster.user_id).all()
    return render_template(
        'apron/shift_roster.html',
        users=users,
        target_date=target_date,
        roster_entries=roster_entries,
        availability_entries=availability_entries,
    )


@apron_bp.route('/staff-deployment', methods=['GET', 'POST'])
@login_required
def staff_deployment():
    shift_date = _parse_iso_date(request.form.get('shift_date') if request.method == 'POST' else request.args.get('shift_date'))
    shift_type = (request.form.get('shift_type') if request.method == 'POST' else request.args.get('shift_type') or 'day').lower()
    if shift_type not in ('day', 'night'):
        shift_type = 'day'

    on_duty_users = _on_duty_users(shift_date, shift_type)
    on_duty_user_ids = {u.id for u in on_duty_users}
    shift_record = Shift.query.filter_by(shift_date=shift_date, shift_type=shift_type).first()
    is_shift_leader = bool(shift_record and shift_record.leader_user_id == current_user.id)
    can_submit = current_user.role in ('admin', 'supervisor') or is_shift_leader

    if request.method == 'POST':
        if not can_submit:
            flash('Only the assigned shift leader (or admin/supervisor) can submit daily deployment.', 'danger')
            return redirect(url_for('apron.staff_deployment', shift_date=shift_date.isoformat(), shift_type=shift_type))

        template = FormTemplate.query.filter_by(form_number=23).first()
        if template:
            role_slots = {
                'apron_runway_inspection': request.form.get('apron_runway_inspection'),
                'enforcement_general_aviation': request.form.get('enforcement_general_aviation'),
                'pbb_operations': request.form.get('pbb_operations'),
                'special_ops_aircraft_turnaround': request.form.get('special_ops_aircraft_turnaround'),
                'works_facilitation': request.form.get('works_facilitation'),
                'general_aircraft_marshalling': request.form.get('general_aircraft_marshalling'),
                'tpbb_operations': request.form.get('tpbb_operations'),
                'general_aviation_marshalling': request.form.get('general_aviation_marshalling'),
                'apron4_operations': request.form.get('apron4_operations'),
                'apron5_operations': request.form.get('apron5_operations'),
                'aodb_desk_calls_information': request.form.get('aodb_desk_calls_information'),
            }

            deployment_names = []
            deployment_ids = []
            for val in role_slots.values():
                if val and val.isdigit():
                    uid = int(val)
                    if uid in on_duty_user_ids:
                        deployment_ids.append(uid)
            deployment_ids = sorted(set(deployment_ids))
            if deployment_ids:
                deployment_names = [u.full_name for u in User.query.filter(User.id.in_(deployment_ids)).order_by(User.full_name).all()]

            data = {
                'shift_date': shift_date.isoformat(),
                'shift_type': shift_type,
                'shift_leader_user_id': shift_record.leader_user_id if shift_record else None,
                'shift_leader_name': shift_record.leader_name if shift_record else None,
                'scheduled_movements': request.form.get('scheduled_movements'),
                'non_scheduled_movements': request.form.get('non_scheduled_movements'),
                'deployed_officer_ids': deployment_ids,
                'deployed_officers': deployment_names,
                'deployment_roles': role_slots,
                'other_deployments': request.form.get('other_deployments'),
            }
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref='Airside',
                data=data,
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)
            db.session.commit()
            flash('Staff deployment plan submitted.', 'success')
        return redirect(url_for('apron.staff_deployment'))

    submissions = FormSubmission.query.join(FormTemplate).filter(
        FormTemplate.form_number == 23
    ).order_by(FormSubmission.created_at.desc()).limit(20).all()
    return render_template(
        'apron/staff_deployment.html',
        submissions=submissions,
        shift_date=shift_date,
        shift_type=shift_type,
        on_duty_users=on_duty_users,
        shift_record=shift_record,
        can_submit=can_submit,
    )


# PBB stands with functional bridges
_PBB_STANDS = {'A1S05': 'PBB 01', 'A1S06': 'PBB 02'}

# Aircraft ICAO type prefixes that are turboprops / non-bridge capable
_NON_BRIDGE_TYPE_PREFIXES = ('AT4', 'AT5', 'AT7', 'AT6', 'AT7', 'DH8', 'DHC', 'SF3',
                              'BE1', 'PA2', 'PA3', 'C208', 'PC12', 'TBM', 'AN2', 'AN4')


def _is_bridge_capable_type(actype: str) -> bool:
    """Return True if the aircraft ICAO type is likely bridge-capable (i.e. a jet)."""
    if not actype:
        return True  # assume capable if unknown
    t = actype.upper().strip()
    return not any(t.startswith(pfx) for pfx in _NON_BRIDGE_TYPE_PREFIXES)


@apron_bp.route('/tpbb-operations', methods=['GET', 'POST'])
@login_required
def tpbb_operations():
    if request.method == 'POST':
        from app.services.aodb_writeback import AodbWritebackService

        template = FormTemplate.query.filter_by(form_number=5).first()
        if template:
            flight_number = request.form.get('flight_number', '').strip()
            docking_time = request.form.get('docking_time', '').strip()
            backoff_time = request.form.get('backoff_time', '').strip()
            bridge_no = request.form.get('bridge_no', '').strip()

            # Determine bridge flag: XOR = red flag; both = ok; neither = no_dock
            has_dock = bool(docking_time)
            has_backoff = bool(backoff_time)
            if has_dock and has_backoff:
                bridge_flag = 'ok'
            elif has_dock or has_backoff:
                bridge_flag = 'incomplete'
            else:
                bridge_flag = 'no_dock'

            # Look up flight in AODB cache for stand/aircraft context
            flight_stand = None
            flight_actype = None
            flight = None
            if flight_number:
                flight = FlightMovement.query.filter_by(flight_number=flight_number).first()
                if flight:
                    flight_stand = (flight.stand or '').strip().upper() or None
                    raw = flight.raw_payload or {}
                    flight_actype = (raw.get('acType') or raw.get('aircraftType') or '').strip() or None

            data = {
                'bridge_no': bridge_no,
                'flight_number': flight_number,
                'pre_arrival_test': request.form.get('pre_arrival_test'),
                'docking_time': docking_time,
                'backoff_time': backoff_time,
                'remarks': request.form.get('remarks'),
                'bridge_flag': bridge_flag,
                'flight_stand': flight_stand,
                'flight_actype': flight_actype,
            }
            submission = FormSubmission(
                form_template_id=template.id,
                status='submitted',
                submitted_by_user_id=current_user.id,
                location_ref='Terminal Apron',
                data=data,
            )
            db.session.add(submission)
            WorkflowService.ensure_issue_for_submission(submission, current_user)
            db.session.flush()  # Get submission.id

            # Flash bridge-flag warning before AODB write-back
            if bridge_flag == 'incomplete':
                missing = 'Back-off Time' if has_dock else 'Docking Time'
                flash(
                    f'\u26a0\ufe0f RED FLAG — Bridge record for {flight_number or bridge_no} is incomplete: '
                    f'{missing} is missing. A record must have both Docking Time and Back-off Time, '
                    f'or neither if the bridge was not used.',
                    'danger',
                )
            elif bridge_flag == 'no_dock' and flight_stand in _PBB_STANDS:
                bridge_capable = _is_bridge_capable_type(flight_actype)
                if bridge_capable:
                    flash(
                        f'Note: {flight_number} is allocated to {flight_stand} ({_PBB_STANDS[flight_stand]}) '
                        f'but no bridge times were recorded. Confirm the bridge was not used.',
                        'warning',
                    )

            # Validate bridge times against flight actual times (ATA/ATD)
            if flight:
                from datetime import datetime
                try:
                    # Docking time (bridge on) must be AFTER ATA
                    if docking_time and flight.arr_or_dep == 'ARR' and flight.actual_datetime:
                        dock_dt = datetime.strptime(docking_time, '%H:%M').time()
                        ata_time = flight.actual_datetime.time()
                        if dock_dt < ata_time:
                            flash(
                                f'⚠️ Warning: Docking Time ({docking_time}) is BEFORE Actual Time of Arrival ({ata_time.strftime("%H:%M")}). '
                                f'Bridge docking should occur after landing.',
                                'warning',
                            )
                    
                    # Back-off time (bridge off) must be BEFORE ATD
                    if backoff_time and flight.arr_or_dep == 'DEP' and flight.actual_datetime:
                        back_dt = datetime.strptime(backoff_time, '%H:%M').time()
                        atd_time = flight.actual_datetime.time()
                        if back_dt > atd_time:
                            flash(
                                f'⚠️ Warning: Back-off Time ({backoff_time}) is AFTER Actual Time of Departure ({atd_time.strftime("%H:%M")}). '
                                f'Bridge should be disconnected before takeoff.',
                                'warning',
                            )
                except (ValueError, AttributeError, TypeError):
                    pass  # Times invalid or unavailable; let AODB write-back handle it

            # Queue write-backs to AODB if flight data available
            if flight:
                # Queue docking time (BTI for arrivals)
                if docking_time and flight.arr_or_dep == 'ARR':
                    try:
                        from datetime import datetime
                        dock_dt = datetime.strptime(docking_time, '%H:%M')
                        if flight.scheduled_datetime:
                            dock_dt = dock_dt.replace(
                                year=flight.scheduled_datetime.year,
                                month=flight.scheduled_datetime.month,
                                day=flight.scheduled_datetime.day,
                            )
                        AodbWritebackService.queue_docking_time(
                            aodb_flight_id=flight.aodb_flight_id,
                            docking_time=dock_dt,
                            form_submission=submission,
                            user=current_user,
                        )
                        flash('Docking time queued for write-back to AODB.', 'info')
                    except (ValueError, AttributeError) as exc:
                        flash(f'Could not queue docking time: {exc}', 'warning')

                # Queue backoff time (BTO for departures)
                if backoff_time and flight.arr_or_dep == 'DEP':
                    try:
                        from datetime import datetime
                        back_dt = datetime.strptime(backoff_time, '%H:%M')
                        if flight.scheduled_datetime:
                            back_dt = back_dt.replace(
                                year=flight.scheduled_datetime.year,
                                month=flight.scheduled_datetime.month,
                                day=flight.scheduled_datetime.day,
                            )
                        AodbWritebackService.queue_backoff_time(
                            aodb_flight_id=flight.aodb_flight_id,
                            backoff_time=back_dt,
                            form_submission=submission,
                            user=current_user,
                        )
                        flash('Back-off time queued for write-back to AODB.', 'info')
                    except (ValueError, AttributeError) as exc:
                        flash(f'Could not queue backoff time: {exc}', 'warning')
            elif flight_number:
                flash(f'Flight {flight_number} not found in AODB cache. Write-back skipped.', 'warning')

            db.session.commit()
            flash('TPBB operation recorded.', 'success')
        return redirect(url_for('apron.tpbb_operations'))

    logs = FormSubmission.query.join(FormTemplate).filter(
        FormTemplate.form_number == 5
    ).order_by(FormSubmission.created_at.desc()).limit(30).all()
    return render_template('apron/tpbb_operations.html', logs=logs, pbb_stands=_PBB_STANDS)
