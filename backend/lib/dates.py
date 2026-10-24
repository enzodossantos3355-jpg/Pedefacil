"""Server-side date helpers. The pod clock is UTC — anchor "today" here, never in the browser."""

import os
from datetime import datetime
from zoneinfo import ZoneInfo


def today_iso(tz: str | None = None) -> str:
    """Today's date as YYYY-MM-DD in `tz` (default: APP_TZ env, else UTC)."""
    zone = tz or os.environ.get("APP_TZ", "UTC")
    return datetime.now(ZoneInfo(zone)).strftime("%Y-%m-%d")


def local_date(dt, tz: str | None = None) -> str:
    """YYYY-MM-DD of a stored datetime (naive = UTC) in the app timezone."""
    from datetime import timezone
    zone = ZoneInfo(tz or os.environ.get("APP_TZ", "UTC"))
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(zone).strftime("%Y-%m-%d")
