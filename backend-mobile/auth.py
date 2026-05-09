from __future__ import annotations

import os

from fastapi import Header, HTTPException, status


_API_KEY = os.getenv("MOBILE_API_KEY", "")


def verify_api_key(x_api_key: str = Header(alias="X-API-Key")) -> None:
    if not _API_KEY:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Server API key not configured")
    if x_api_key != _API_KEY:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")
