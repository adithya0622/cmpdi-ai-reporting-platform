"""Notification service: email (SMTP) and webhook dispatch for key platform events.
Air-gap safe — only fires when SMTP or webhook is configured."""
import json
import logging
import smtplib
import urllib.request
from email.mime.text import MIMEText

from ..config import settings

log = logging.getLogger(__name__)


def _smtp_configured() -> bool:
    return bool(getattr(settings, "smtp_host", ""))


def _webhook_configured() -> bool:
    return bool(getattr(settings, "webhook_url", ""))


def send_email(subject: str, body: str, to: list[str] | None = None) -> bool:
    if not _smtp_configured():
        return False
    recipients = to or [r.strip() for r in (settings.notification_emails or "").split(",") if r.strip()]
    if not recipients:
        return False
    try:
        msg = MIMEText(body, "plain", "utf-8")
        msg["Subject"] = f"[CMPDI Platform] {subject}"
        msg["From"] = settings.smtp_from or f"cmpdi@{settings.smtp_host}"
        msg["To"] = ", ".join(recipients)
        with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as srv:
            if settings.smtp_user:
                srv.starttls()
                srv.login(settings.smtp_user, settings.smtp_password)
            srv.send_message(msg)
        log.info("Email sent: %s → %s", subject, recipients)
        return True
    except Exception:
        log.warning("Email send failed: %s", subject, exc_info=True)
        return False


def fire_webhook(event: str, data: dict) -> bool:
    if not _webhook_configured():
        return False
    try:
        payload = json.dumps({"event": event, "data": data}, default=str).encode()
        req = urllib.request.Request(
            settings.webhook_url,
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)
        log.info("Webhook fired: %s", event)
        return True
    except Exception:
        log.warning("Webhook failed: %s", event, exc_info=True)
        return False


def notify(event: str, subject: str, body: str, data: dict | None = None) -> None:
    send_email(subject, body)
    fire_webhook(event, data or {"subject": subject, "body": body})
