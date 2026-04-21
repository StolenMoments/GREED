from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


SEOUL_TZ = ZoneInfo("Asia/Seoul")


def seoul_now() -> datetime:
    return datetime.now(SEOUL_TZ)
