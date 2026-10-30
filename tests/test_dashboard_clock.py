from datetime import datetime, timezone
from unittest.mock import patch
import pytest
from app.dashboard_clock import clock_snapshot


@pytest.mark.parametrize('utc, expected_date, expected_time', [
    ('2026-01-01T02:59:59+00:00', '31/12/2025', '23:59:59'),
    ('2026-01-01T03:00:00+00:00', '01/01/2026', '00:00:00'),
    ('2026-07-01T15:30:45+00:00', '01/07/2026', '12:30:45'),
])
def test_paraguay_clock_and_date_rollover(utc, expected_date, expected_time):
    instant = datetime.fromisoformat(utc)
    with patch('app.dashboard_clock.datetime') as clock:
        clock.now.return_value = instant
        snapshot = clock_snapshot()
        clock.now.assert_called_once_with(timezone.utc)
    assert snapshot['timezone'] == 'America/Asuncion'
    assert snapshot['date'] == expected_date
    assert snapshot['time'] == expected_time
    assert snapshot['utc_offset_seconds'] == -10800
    assert snapshot['epoch_ms'] == int(instant.timestamp() * 1000)
