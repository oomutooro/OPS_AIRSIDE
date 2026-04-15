"""
AodbWritebackService — processes the write-back queue to sync app data back to AODB.

Usage:
    # Queue a write-back
    AodbWritebackService.queue_docking_time(flight_id, docking_time, submission, user)
    
    # Process queue (called by background scheduler)
    AodbWritebackService.process_queue()
"""
import logging
from datetime import datetime
from typing import Optional

from app import db
from app.models.flight import AodbWriteback, FlightMovement
from app.services.aodb_client import AodbClient

logger = logging.getLogger(__name__)


class AodbWritebackService:
    """Manage write-back queue and submission to AODB."""

    # ------------------------------------------------------------------
    # Queue management
    # ------------------------------------------------------------------

    @classmethod
    def queue_docking_time(
        cls,
        aodb_flight_id: str,
        docking_time: datetime,
        form_submission=None,
        user=None,
    ) -> AodbWriteback:
        """Queue TPBB bridge docking time for write-back (BTI for arrivals)."""
        from app.services.aodb_client import _fmt_dt
        return AodbWriteback.queue_writeback(
            aodb_flight_id=aodb_flight_id,
            writeback_type='bridge_docking',
            aodb_field_name='BTI',
            aodb_value=_fmt_dt(docking_time),
            form_submission_id=form_submission.id if form_submission else None,
            user_id=user.id if user else None,
        )

    @classmethod
    def queue_backoff_time(
        cls,
        aodb_flight_id: str,
        backoff_time: datetime,
        form_submission=None,
        user=None,
    ) -> AodbWriteback:
        """Queue TPBB bridge backoff time for write-back (BTO for departures)."""
        from app.services.aodb_client import _fmt_dt
        return AodbWriteback.queue_writeback(
            aodb_flight_id=aodb_flight_id,
            writeback_type='bridge_backoff',
            aodb_field_name='BTO',
            aodb_value=_fmt_dt(backoff_time),
            form_submission_id=form_submission.id if form_submission else None,
            user_id=user.id if user else None,
        )

    @classmethod
    def queue_stand_assignment(
        cls,
        aodb_flight_id: str,
        stand_code: str,
        form_submission=None,
        user=None,
    ) -> AodbWriteback:
        """Queue stand assignment for write-back (if AODB supports it)."""
        return AodbWriteback.queue_writeback(
            aodb_flight_id=aodb_flight_id,
            writeback_type='stand_assignment',
            aodb_field_name='stand',
            aodb_value=stand_code,
            form_submission_id=form_submission.id if form_submission else None,
            user_id=user.id if user else None,
        )

    # ------------------------------------------------------------------
    # Processing
    # ------------------------------------------------------------------

    @classmethod
    def process_queue(cls, batch_size: int = 10) -> dict:
        """
        Process pending write-backs in batch.
        Returns summary of processed items.
        """
        result = {
            'pending': 0,
            'processed': 0,
            'succeeded': 0,
            'failed': 0,
            'errors': [],
        }

        # Get pending items
        pending = (
            AodbWriteback.query
            .filter_by(status='pending')
            .order_by(AodbWriteback.created_at)
            .limit(batch_size)
            .all()
        )
        result['pending'] = len(pending)

        if not pending:
            logger.info('AODB write-back queue is empty.')
            return result

        try:
            client = AodbClient.from_app_config()
        except ValueError as exc:
            result['errors'].append(f'AODB not configured: {exc}')
            return result

        for item in pending:
            try:
                cls._process_item(item, client)
                result['succeeded'] += 1
            except Exception as exc:
                result['failed'] += 1
                result['errors'].append(f'{item.id}: {str(exc)[:100]}')
                logger.warning('Error processing write-back %d: %s', item.id, exc)
            finally:
                result['processed'] += 1

        db.session.commit()
        logger.info(
            'AODB write-back batch: %d processed, %d succeeded, %d failed',
            result['processed'], result['succeeded'], result['failed'],
        )
        return result

    @classmethod
    def _process_item(cls, item: AodbWriteback, client: AodbClient):
        """Process a single write-back item."""
        item.status = 'in_progress'
        item.last_attempted_at = datetime.utcnow()

        try:
            if item.writeback_type in ('bridge_docking', 'bridge_backoff'):
                # Time write-back via movementtime endpoint
                response = client.write_movement_time(
                    flight_id=item.aodb_flight_id,
                    time_type=item.aodb_field_name,  # 'BTI', 'BTO', etc.
                    time_value=item.aodb_value,  # YYYYMMDDHH24MI
                )
                item.aodb_response = response
                item.status = 'completed'
                item.completed_at = datetime.utcnow()
                logger.info(
                    'Write-back completed: %s flight=%s field=%s value=%s',
                    item.writeback_type, item.aodb_flight_id, item.aodb_field_name,
                    item.aodb_value,
                )
            else:
                # Other types not yet supported
                raise NotImplementedError(f'Writeback type {item.writeback_type} not implemented')

        except Exception as exc:
            item.retry_count += 1
            item.error_message = str(exc)[:500]
            if item.can_retry():
                item.status = 'failed'
                logger.info(
                    'Write-back failed, will retry: %s (attempt %d/%d)',
                    item.id, item.retry_count, item.max_retries,
                )
            else:
                item.status = 'failed_permanent'
                logger.warning(
                    'Write-back permanent failure after %d retries: %s: %s',
                    item.retry_count, item.id, exc,
                )
            raise  # Re-raise to propagate to caller's exception handler

    # ------------------------------------------------------------------
    # Monitoring
    # ------------------------------------------------------------------

    @classmethod
    def get_queue_status(cls) -> dict:
        """Get summary statistics of the write-back queue."""
        total = AodbWriteback.query.count()
        pending = AodbWriteback.query.filter_by(status='pending').count()
        in_progress = AodbWriteback.query.filter_by(status='in_progress').count()
        completed = AodbWriteback.query.filter_by(status='completed').count()
        failed = AodbWriteback.query.filter_by(status='failed').count()
        failed_permanent = AodbWriteback.query.filter_by(status='failed_permanent').count()

        return {
            'total': total,
            'pending': pending,
            'in_progress': in_progress,
            'completed': completed,
            'failed': failed,
            'failed_permanent': failed_permanent,
        }

    @classmethod
    def get_recent_items(cls, limit: int = 50) -> list:
        """Get recent write-back items (for monitoring page)."""
        return (
            AodbWriteback.query
            .order_by(AodbWriteback.created_at.desc())
            .limit(limit)
            .all()
        )

    @classmethod
    def get_failed_items(cls) -> list:
        """Get all failed items eligible for retry."""
        return AodbWriteback.query.filter(AodbWriteback.can_retry()).all()

    @classmethod
    def retry_failed_items(cls) -> dict:
        """Manually retry all failed items that haven't exceeded max retries."""
        failed = cls.get_failed_items()
        if not failed:
            return {'retried': 0, 'message': 'No failed items to retry'}

        for item in failed:
            item.status = 'pending'
        db.session.commit()
        return {'retried': len(failed), 'message': f'Marked {len(failed)} items for retry'}
