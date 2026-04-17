"""Workflow service for hierarchical issue escalation and dashboard metrics."""
from datetime import datetime, timedelta
from sqlalchemy import case, func
from app import db
from app.models.form import IssueWorkflow


class WorkflowService:
    """Business logic for escalation queues and management visibility."""

    @staticmethod
    def ensure_issue_for_submission(submission, reporter):
        """Create workflow item once per submission."""
        db.session.flush()
        existing = IssueWorkflow.query.filter_by(submission_id=submission.id).first()
        if existing:
            return existing
        issue = IssueWorkflow.create_from_submission(submission, reporter)
        db.session.add(issue)
        return issue

    @staticmethod
    def _scope_query_for_user(user):
        q = IssueWorkflow.query
        if user.role == 'admin':
            return q
        if user.role == 'supervisor':
            if user.department:
                return q.filter(IssueWorkflow.department == user.department)
            return q
        return q.filter(IssueWorkflow.department == user.department) if user.department else q

    @staticmethod
    def dashboard_data_for_user(user):
        scope_q = WorkflowService._scope_query_for_user(user)

        if user.role in ('admin', 'supervisor'):
            pending_directed_q = scope_q.filter(
                IssueWorkflow.status != 'closed',
                IssueWorkflow.current_owner_role == 'supervisor',
            )
        else:
            pending_directed_q = scope_q.filter(
                IssueWorkflow.status != 'closed',
                IssueWorkflow.current_owner_role == user.role,
            )

        pending_directed = pending_directed_q.order_by(IssueWorkflow.last_transition_at.desc()).limit(25).all()
        closed_recent = scope_q.filter(IssueWorkflow.status == 'closed').order_by(IssueWorkflow.closed_at.desc()).limit(25).all()

        now = datetime.utcnow()
        cur_start = now - timedelta(days=30)
        prev_start = now - timedelta(days=60)

        opened_current = scope_q.filter(IssueWorkflow.opened_at >= cur_start).count()
        opened_prev = scope_q.filter(IssueWorkflow.opened_at >= prev_start, IssueWorkflow.opened_at < cur_start).count()
        closed_current = scope_q.filter(IssueWorkflow.closed_at >= cur_start).count()
        closed_prev = scope_q.filter(IssueWorkflow.closed_at >= prev_start, IssueWorkflow.closed_at < cur_start).count()

        current_rate = round((closed_current / opened_current) * 100, 1) if opened_current else 100.0
        prev_rate = round((closed_prev / opened_prev) * 100, 1) if opened_prev else 100.0
        improvement = round(current_rate - prev_rate, 1)

        role_breakdown = dict(
            scope_q.filter(IssueWorkflow.status != 'closed')
            .with_entities(IssueWorkflow.current_owner_role, func.count(IssueWorkflow.id))
            .group_by(IssueWorkflow.current_owner_role)
            .all()
        )

        dept_rows = scope_q.with_entities(
            IssueWorkflow.department,
            func.count(IssueWorkflow.id),
            func.sum(case((IssueWorkflow.status == 'closed', 1), else_=0)),
        ).group_by(IssueWorkflow.department).all()
        department_overview = [
            {
                'department': row[0] or 'Unassigned',
                'total': int(row[1] or 0),
                'closed': int(row[2] or 0),
                'open': int((row[1] or 0) - (row[2] or 0)),
            }
            for row in dept_rows
        ]

        return {
            'pending_directed': pending_directed,
            'closed_recent': closed_recent,
            'workflow_stats': {
                'opened_current_30d': opened_current,
                'closed_current_30d': closed_current,
                'open_backlog': scope_q.filter(IssueWorkflow.status != 'closed').count(),
                'resolution_rate': current_rate,
                'improvement_delta': improvement,
            },
            'role_breakdown': role_breakdown,
            'department_overview': department_overview,
        }
