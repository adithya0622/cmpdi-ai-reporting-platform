from ..db import SessionLocal
from ..models import AuditLog


def log(action: str, username: str = "", detail: dict | None = None) -> None:
    """Audit trail write. Never raises - auditing must not break the request path."""
    try:
        db = SessionLocal()
        try:
            db.add(AuditLog(username=username or "", action=action, detail=detail or {}))
            db.commit()
        finally:
            db.close()
    except Exception:
        pass
