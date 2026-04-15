"""
AodbClient — HTTP wrapper for the AODB REST API.

Endpoint pattern (from AODB REST API 설계서 v1.4):
  POST http://{host}:{port}/standapi/login
  POST http://{host}:{port}/standapi/logout
  POST http://{host}:{port}/standapi/arrmovementinfo
  POST http://{host}:{port}/standapi/depmovementinfo
  POST http://{host}:{port}/standapi/movementtime

All requests send JSON; all responses return JSON with top-level
{resultCode, resultMessage, data: [...]}.

Datetime format: YYYYMMDDHH24MI  (e.g. "202604101430")
"""
import logging
from datetime import datetime, date
import random
from typing import Optional
import requests

logger = logging.getLogger(__name__)

_AODB_DT_FMT = '%Y%m%d%H%M'


def _fmt_dt(dt: datetime) -> str:
    return dt.strftime(_AODB_DT_FMT)


def _make_window(for_date: date) -> tuple[str, str]:
    """Return (from_datetime, to_datetime) strings covering the full day."""
    from_dt = datetime(for_date.year, for_date.month, for_date.day, 0, 0)
    to_dt = datetime(for_date.year, for_date.month, for_date.day, 23, 59)
    return _fmt_dt(from_dt), _fmt_dt(to_dt)


class AodbClient:
    """
    Session-aware client for the AODB REST API.
    Use as a context manager to ensure logout:

        with AodbClient.from_app_config(app) as client:
            arrivals = client.get_arrivals(date.today())
    """

    def __init__(
        self,
        base_url: str,
        user_id: str = '',
        password: str = '',
        timeout: int = 30,
        mock_mode: bool = False,
        mock_writeback_fail_rate: float = 0.0,
        auth_key: str = '',
    ):
        if not base_url:
            raise ValueError('AODB base_url is required.')
        if not auth_key and (not user_id or not password):
            raise ValueError('AODB requires either auth_key or user_id/password.')
        self._base_url = base_url.rstrip('/')
        self._user_id = user_id
        self._password = password
        self._auth_key = (auth_key or '').strip()
        self._timeout = timeout
        self._mock_mode = mock_mode
        self._mock_writeback_fail_rate = max(0.0, min(1.0, float(mock_writeback_fail_rate)))
        self._session_id: Optional[str] = None
        self._http = requests.Session()
        if self._auth_key:
            self._http.headers.update({'X-Authentication-Key': self._auth_key})

    # ------------------------------------------------------------------
    # Context manager support
    # ------------------------------------------------------------------

    def __enter__(self):
        self.login()
        return self

    def __exit__(self, *_):
        try:
            self.logout()
        except Exception:
            pass

    # ------------------------------------------------------------------
    # Factory
    # ------------------------------------------------------------------

    @classmethod
    def from_app_config(cls, app=None) -> 'AodbClient':
        """Create client from Flask app config (or current_app if app is None)."""
        from flask import current_app
        cfg = (app or current_app)._get_current_object().config
        base_url = cfg.get('AODB_BASE_URL', '')
        auth_key = (cfg.get('AODB_AUTH_KEY', '') or '').strip()
        user_id  = cfg.get('AODB_USER_ID', '')
        password = cfg.get('AODB_PASSWORD', '')
        timeout  = int(cfg.get('AODB_TIMEOUT_SECONDS', 30))
        mock_mode = bool(cfg.get('AODB_MOCK_MODE', False))
        mock_writeback_fail_rate = float(cfg.get('AODB_MOCK_WRITEBACK_FAIL_RATE', 0.0) or 0.0)
        return cls(
            base_url,
            user_id,
            password,
            timeout,
            mock_mode=mock_mode,
            mock_writeback_fail_rate=mock_writeback_fail_rate,
            auth_key=auth_key,
        )

    # ------------------------------------------------------------------
    # Auth
    # ------------------------------------------------------------------

    def login(self) -> str:
        """POST /standapi/login — obtain sessionId."""
        if self._mock_mode:
            self._session_id = f'mock-{datetime.utcnow().strftime("%Y%m%d%H%M%S")}'
            logger.info('AODB mock mode: login simulated.')
            return self._session_id

        if self._auth_key:
            self._session_id = 'auth-key'
            logger.info('AODB key auth mode enabled: login skipped.')
            return self._session_id

        payload = {'userId': self._user_id, 'password': self._password}
        data = self._post('/standapi/login', payload)
        session_id = (data.get('sessionId') or data.get('data', {}).get('sessionId', ''))
        if not session_id:
            raise RuntimeError(f'AODB login failed — no sessionId in response: {data}')
        self._session_id = session_id
        logger.info('AODB login OK, sessionId acquired.')
        return session_id

    def logout(self):
        """POST /standapi/logout."""
        if not self._session_id:
            return
        if self._mock_mode:
            self._session_id = None
            logger.info('AODB mock mode: logout simulated.')
            return
        if self._auth_key:
            self._session_id = None
            logger.info('AODB key auth mode enabled: logout skipped.')
            return
        try:
            self._post('/standapi/logout', {'sessionId': self._session_id})
        finally:
            self._session_id = None
        logger.info('AODB logout OK.')

    # ------------------------------------------------------------------
    # Flight queries
    # ------------------------------------------------------------------

    def get_arrivals(self, for_date: date) -> list[dict]:
        """
        POST /standapi/arrmovementinfo — all arrivals within the day window.
        Returns list of arrMovementInfo dicts.
        """
        if self._mock_mode:
            return self._mock_movements(for_date, 'ARR')

        if not self._auth_key and not self._session_id:
            self.login()

        from_dt, to_dt = _make_window(for_date)
        payload = {'fromDatetime': from_dt, 'toDatetime': to_dt}
        if self._session_id and not self._auth_key:
            payload['sessionId'] = self._session_id
        data = self._post('/standapi/arrmovementinfo', payload)
        return self._extract_list(data)

    def get_departures(self, for_date: date) -> list[dict]:
        """
        POST /standapi/depmovementinfo — all departures within the day window.
        Returns list of depMovementInfo dicts.
        """
        if self._mock_mode:
            return self._mock_movements(for_date, 'DEP')

        if not self._auth_key and not self._session_id:
            self.login()

        from_dt, to_dt = _make_window(for_date)
        payload = {'fromDatetime': from_dt, 'toDatetime': to_dt}
        if self._session_id and not self._auth_key:
            payload['sessionId'] = self._session_id
        data = self._post('/standapi/depmovementinfo', payload)
        return self._extract_list(data)

    def write_movement_time(self, flight_id: str, time_type: str, time_value):
        """
        POST /standapi/movementtime — write actual ground event time back to AODB.
        time_type: e.g. 'ATA', 'ATD', 'BTI', 'BTO', etc.
        time_value: datetime or YYYYMMDDHH24MI string
        """
        from datetime import datetime as dt
        if isinstance(time_value, dt):
            time_str = _fmt_dt(time_value)
        else:
            time_str = str(time_value)
        
        if not self._auth_key and not self._session_id:
            self.login()

        payload = {
            'flightId': flight_id,
            'timeType': time_type,
            'timeValue': time_str,
        }
        if self._session_id and not self._auth_key:
            payload['sessionId'] = self._session_id

        if self._mock_mode:
            # Optional fail rate allows local retry-flow testing.
            if self._mock_writeback_fail_rate > 0 and random.random() < self._mock_writeback_fail_rate:
                raise RuntimeError('AODB mock mode injected failure for retry testing.')
            return {
                'resultCode': '0',
                'resultMessage': 'MOCK_SUCCESS',
                'data': {
                    'sessionId': self._session_id,
                    'flightId': flight_id,
                    'timeType': time_type,
                    'timeValue': time_str,
                    'mode': 'mock',
                },
            }

        return self._post('/standapi/movementtime', payload)

    # ------------------------------------------------------------------
    # Internal HTTP
    # ------------------------------------------------------------------

    def _post(self, path: str, payload: dict) -> dict:
        url = f'{self._base_url}{path}'
        try:
            resp = self._http.post(url, json=payload, timeout=self._timeout)
            resp.raise_for_status()
            body = resp.json()
        except requests.exceptions.ConnectionError as exc:
            raise RuntimeError(f'AODB connection failed ({url}): {exc}') from exc
        except requests.exceptions.Timeout:
            raise RuntimeError(f'AODB request timed out ({url})') from None
        except requests.exceptions.HTTPError as exc:
            raise RuntimeError(f'AODB HTTP error {exc.response.status_code} ({url})') from exc

        result_code = str(body.get('resultCode', '')).strip()
        result_msg  = body.get('resultMessage', '')
        if result_code not in ('', '0', '200', 'OK', 'SUCCESS', 'success'):
            raise RuntimeError(f'AODB error {result_code}: {result_msg}')
        return body

    @staticmethod
    def _extract_list(body: dict) -> list[dict]:
        """Pull the movement list from the AODB response envelope."""
        data = body.get('data')
        if isinstance(data, list):
            return data
        if isinstance(data, dict):
            # Some endpoints wrap in {"list": [...]}
            for key in ('list', 'arrMovementInfoList', 'depMovementInfoList', 'movementList'):
                if isinstance(data.get(key), list):
                    return data[key]
        return []

    @staticmethod
    def _mock_movements(for_date: date, arr_or_dep: str) -> list[dict]:
        """Return deterministic sample flights for offline/local development."""
        date_ymd = for_date.strftime('%Y%m%d')
        terminal = 'T1'

        arr = [
            {
                'flightId': f'MOCK-ARR-{date_ymd}-01',
                'flightIataCode': 'UR201',
                'flightIcaoCode': 'UGA201',
                'airlineName': 'Uganda Airlines',
                'flightNumber': 'UR201',
                'callsign': 'UGA201',
                'scheduledDate': date_ymd,
                'scheduledTime': f'{date_ymd}0815',
                'estimatedTime': f'{date_ymd}0825',
                'ATA': '',
                'RPI': '',
                'SPI': '',
                'BTI': '',
                'originAirport': 'NBO',
                'destinationAirport': 'EBB',
                'terminal': terminal,
                'stand': 'A03',
                'operationStatus': 'SCHEDULED',
            },
            {
                'flightId': f'MOCK-ARR-{date_ymd}-02',
                'flightIataCode': 'ET338',
                'flightIcaoCode': 'ETH338',
                'airlineName': 'Ethiopian Airlines',
                'flightNumber': 'ET338',
                'callsign': 'ETH338',
                'scheduledDate': date_ymd,
                'scheduledTime': f'{date_ymd}1140',
                'estimatedTime': f'{date_ymd}1150',
                'ATA': '',
                'RPI': '',
                'SPI': '',
                'BTI': '',
                'originAirport': 'ADD',
                'destinationAirport': 'EBB',
                'terminal': terminal,
                'stand': 'B02',
                'operationStatus': 'SCHEDULED',
            },
            {
                'flightId': f'MOCK-ARR-{date_ymd}-03',
                'flightIataCode': 'KQ418',
                'flightIcaoCode': 'KQA418',
                'airlineName': 'Kenya Airways',
                'flightNumber': 'KQ418',
                'callsign': 'KQA418',
                'scheduledDate': date_ymd,
                'scheduledTime': f'{date_ymd}1530',
                'estimatedTime': f'{date_ymd}1540',
                'ATA': '',
                'RPI': '',
                'SPI': '',
                'BTI': '',
                'originAirport': 'NBO',
                'destinationAirport': 'EBB',
                'terminal': terminal,
                'stand': 'A01',
                'operationStatus': 'SCHEDULED',
            },
        ]

        dep = [
            {
                'flightId': f'MOCK-DEP-{date_ymd}-01',
                'flightIataCode': 'UR202',
                'flightIcaoCode': 'UGA202',
                'airlineName': 'Uganda Airlines',
                'flightNumber': 'UR202',
                'callsign': 'UGA202',
                'scheduledDate': date_ymd,
                'scheduledTime': f'{date_ymd}0945',
                'estimatedTime': f'{date_ymd}0955',
                'ATD': '',
                'BTO': '',
                'SPO': '',
                'RPO': '',
                'originAirport': 'EBB',
                'destinationAirport': 'NBO',
                'terminal': terminal,
                'stand': 'A03',
                'operationStatus': 'SCHEDULED',
            },
            {
                'flightId': f'MOCK-DEP-{date_ymd}-02',
                'flightIataCode': 'ET339',
                'flightIcaoCode': 'ETH339',
                'airlineName': 'Ethiopian Airlines',
                'flightNumber': 'ET339',
                'callsign': 'ETH339',
                'scheduledDate': date_ymd,
                'scheduledTime': f'{date_ymd}1310',
                'estimatedTime': f'{date_ymd}1320',
                'ATD': '',
                'BTO': '',
                'SPO': '',
                'RPO': '',
                'originAirport': 'EBB',
                'destinationAirport': 'ADD',
                'terminal': terminal,
                'stand': 'B02',
                'operationStatus': 'SCHEDULED',
            },
            {
                'flightId': f'MOCK-DEP-{date_ymd}-03',
                'flightIataCode': 'KQ419',
                'flightIcaoCode': 'KQA419',
                'airlineName': 'Kenya Airways',
                'flightNumber': 'KQ419',
                'callsign': 'KQA419',
                'scheduledDate': date_ymd,
                'scheduledTime': f'{date_ymd}1735',
                'estimatedTime': f'{date_ymd}1745',
                'ATD': '',
                'BTO': '',
                'SPO': '',
                'RPO': '',
                'originAirport': 'EBB',
                'destinationAirport': 'NBO',
                'terminal': terminal,
                'stand': 'A01',
                'operationStatus': 'SCHEDULED',
            },
        ]

        return arr if arr_or_dep.upper() == 'ARR' else dep
