from fastapi import Header, HTTPException

from .config import settings


def require_auth(x_api_token: str | None = Header(default=None)):
    if settings.api_token and x_api_token != settings.api_token:
        raise HTTPException(status_code=401, detail="invalid or missing API token")
