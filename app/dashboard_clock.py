"""Hora del servidor y reglas IANA: independiente del reloj/zona del cliente."""
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

PARAGUAY_TIMEZONE = ZoneInfo('America/Asuncion')


def clock_snapshot():
    now = datetime.now(timezone.utc)
    local = now.astimezone(PARAGUAY_TIMEZONE)
    return {
        'epoch_ms': int(now.timestamp() * 1000),
        'utc_offset_seconds': int(local.utcoffset().total_seconds()),
        'timezone': PARAGUAY_TIMEZONE.key,
        'date': local.strftime('%d/%m/%Y'),
        'time': local.strftime('%H:%M:%S'),
        'iso': local.isoformat(timespec='seconds'),
    }
