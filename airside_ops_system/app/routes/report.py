"""
Reporting routes: daily ops report, analytics dashboard, custom report builder, exports.
"""
from io import BytesIO
from datetime import date
from flask import Blueprint, Response, flash, redirect, render_template, request, send_file, url_for
from flask_login import login_required
from app.models.form import FormSubmission, FormTemplate
from app.services.export_service import ExportService
from app.services.analytics_service import AnalyticsService
from app.services.pdf_generator import PDFGeneratorService

report_bp = Blueprint('report', __name__)


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
                submitted_by_user_id=request.form.get('submitted_by_user_id') or None,
                location_ref='Airside Ops',
                data=request.form.to_dict(flat=False),
            )
            db.session.add(submission)
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
