"""
Email Agent — SendGrid integration with approval workflow.
"""
import sendgrid
from sendgrid.helpers.mail import Mail, Email, To, Content
from config import settings
from database import SessionLocal, EmailLog
from datetime import datetime


def send_email(to_email: str, subject: str, html_body: str, lead_id: int = None) -> dict:
    """Send an email via SendGrid."""
    db = SessionLocal()
    log = EmailLog(
        lead_id=lead_id,
        to_email=to_email,
        subject=subject,
        body_preview=html_body[:500],
        status="pending"
    )
    db.add(log)
    db.commit()

    try:
        if not settings.sendgrid_api_key:
            log.status = "no_api_key"
            db.commit()
            return {"status": "skipped", "reason": "No SendGrid API key configured"}

        sg = sendgrid.SendGridAPIClient(api_key=settings.sendgrid_api_key)
        message = Mail(
            from_email=Email(settings.sendgrid_from_email, settings.sendgrid_from_name),
            to_emails=To(to_email),
            subject=subject,
            html_content=Content("text/html", html_body)
        )
        response = sg.client.mail.send.post(request_body=message.get())

        log.status = "sent"
        log.sent_at = datetime.utcnow()
        db.commit()
        return {"status": "sent", "status_code": response.status_code}
    except Exception as e:
        log.status = "failed"
        db.commit()
        return {"status": "failed", "error": str(e)}
    finally:
        db.close()


def queue_email_for_approval(to_email: str, subject: str, html_body: str, lead_id: int = None) -> int:
    """Queue email for human review before sending."""
    db = SessionLocal()
    log = EmailLog(
        lead_id=lead_id,
        to_email=to_email,
        subject=subject,
        body_preview=html_body[:2000],
        status="pending_approval"
    )
    db.add(log)
    db.commit()
    email_id = log.id
    db.close()
    return email_id


def approve_and_send_email(email_log_id: int) -> dict:
    """Approve a queued email and send it."""
    db = SessionLocal()
    log = db.query(EmailLog).filter(EmailLog.id == email_log_id).first()
    if not log:
        db.close()
        return {"error": "Email not found"}
    if log.status != "pending_approval":
        db.close()
        return {"error": f"Email is not pending approval (status: {log.status})"}

    result = send_email(log.to_email, log.subject, log.body_preview, log.lead_id)
    log.status = result["status"]
    if result["status"] == "sent":
        log.sent_at = datetime.utcnow()
    db.commit()
    db.close()
    return result
