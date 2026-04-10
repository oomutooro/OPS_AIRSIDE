"""
AodbSyncService — orchestrates syncing flight data from AODB into FlightMovement table.

Usage (manual):
    result = AodbSyncService.sync_date(date.today())

Usage (scheduled — called by APScheduler):
    AodbSyncService.scheduled_sync()
"""
import logging
from datetime import date, datetime, timedelta
from typing import Optional

from app import db
from app.models.flight import FlightMovement
from app.services.aodb_client import AodbClient

logger = logging.getLogger(__name__)


class AodbSyncService:
    """Fetch flights from AODB and upsert into local FlightMovement table."""

    # ------------------------------------------------------------------
    # Public entry points
    # ------------------------------------------------------------------

    @classmethod
    def sync_date(cls, for_date: date, app=None) -> dict:
        """
        Sync arrivals and departures for one calendar date.

        Returns:
            {
                'date':       'YYYY-MM-DD',
                'arrivals':   <count fetched from AODB>,
                'departures': <count fetched from AODB>,
                'upserted':   <count written to DB>,
                'errors':     [list of error strings],
                'synced_at':  ISO timestamp,
            }
        """
        result = {
            'date': for_date.isoformat(),
            'arrivals': 0,
            'departures': 0,
            'upserted': 0,
            'errors': [],
            'synced_at': datetime.utcnow().isoformat(),
        }

        try:
            client = AodbClient.from_app_config(app)
        except ValueError as exc:
            result['errors'].append(f'AODB not configured: {exc}')
            return result

        try:
            with client as c:
                arrivals = c.get_arrivals(for_date)
                result['arrivals'] = len(arrivals)

                departures = c.get_departures(for_date)
                result['departures'] = len(departures)

                upserted = cls._bulk_upsert(arrivals, 'ARR')
                upserted += cls._bulk_upsert(departures, 'DEP')
                db.session.commit()
                result['upserted'] = upserted

        except RuntimeError as exc:
            db.session.rollback()
            result['errors'].append(str(exc))
            logger.warning('AODB sync error for %s: %s', for_date.isoformat(), exc)

        logger.info(
            'AODB sync %s: ARR=%d DEP=%d upserted=%d errors=%d',
            for_date.isoformat(), result['arrivals'], result['departures'],
            result['upserted'], len(result['errors']),
        )
        return result

    @classmethod
    def scheduled_sync(cls):
        """
        Entry point called by APScheduler — syncs today and tomorrow.
        Must be called within Flask app context.
        """
        today = date.today()
        tomorrow = today + timedelta(days=1)
        for d in (today, tomorrow):
            cls.sync_date(d)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @classmethod
    def _bulk_upsert(cls, records: list[dict], arr_or_dep: str) -> int:
        count = 0
        for rec in records:
            try:
                obj = FlightMovement.upsert_from_aodb(rec, arr_or_dep)
                if obj is not None:
                    count += 1
            except Exception as exc:
                logger.debug('Skipping record %s: %s', rec.get('flightId'), exc)
        return count

    # ------------------------------------------------------------------
    # Read helpers (for routes/templates)
    # ------------------------------------------------------------------

    @classmethod
    def flights_for_date(cls, for_date: date, arr_or_dep: Optional[str] = None) -> list[FlightMovement]:
        """Return cached flight movements for a given date, sorted by scheduled time."""
        date_str = for_date.strftime('%Y%m%d')
        q = FlightMovement.query.filter(FlightMovement.scheduled_date == date_str)
        if arr_or_dep:
            q = q.filter(FlightMovement.arr_or_dep == arr_or_dep.upper())
        return q.order_by(FlightMovement.scheduled_datetime).all()

    @classmethod
    def last_sync_time(cls) -> Optional[datetime]:
        """Return the most recent `synced_at` across all cached records."""
        row = db.session.query(db.func.max(FlightMovement.synced_at)).scalar()
        return row

    @classmethod
    def flight_numbers_for_date(cls, for_date: date) -> list[str]:
        """Distinct flight numbers for dropdown population."""
        date_str = for_date.strftime('%Y%m%d')
        rows = (
            db.session.query(FlightMovement.flight_number, FlightMovement.arr_or_dep,
                             FlightMovement.airline_name)
            .filter(FlightMovement.scheduled_date == date_str)
            .filter(FlightMovement.flight_number.isnot(None))
            .order_by(FlightMovement.scheduled_datetime)
            .all()
        )
        seen = set()
        result = []
        for fn, ad, al in rows:
            if fn not in seen:
                seen.add(fn)
                result.append({'flight_number': fn, 'arr_or_dep': ad, 'airline': al or ''})
        return result
