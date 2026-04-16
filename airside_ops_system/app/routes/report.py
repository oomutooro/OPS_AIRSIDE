"""
Reporting routes: daily ops report, analytics dashboard, custom report builder, exports.
"""
from io import BytesIO
from datetime import date, datetime
from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from app.models.form import FormSubmission, FormTemplate
from app.models.reference import Company
from app.services.export_service import ExportService
from app.services.analytics_service import AnalyticsService
from app.services.pdf_generator import PDFGeneratorService
from app.services.workflow_service import WorkflowService
from flask_login import current_user

report_bp = Blueprint('report', __name__)


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
