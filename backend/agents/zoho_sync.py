"""
Zoho Mail → NOVA sync.

Watches the cold-email mailbox (aiwithruth@aisavesyoutime.com) over IMAP and logs
everything into NOVA so the CRM shows the whole story:

- Sent folder  → outbound email logged against the matching lead (last_contact stamped)
- Inbox        → a reply flips the matching lead to hot and logs an inbound activity

Emails to/from people who are not leads (warmup emails to friends) are remembered in
synced_emails so they are never reprocessed, but they do not create CRM noise.

Requires in .env:
  ZOHO_EMAIL=aiwithruth@aisavesyoutime.com
  ZOHO_APP_PASSWORD=<app-specific password from Zoho, never the real password>
"""
import imaplib
import email
from email.header import decode_header
from email.utils import parseaddr, parsedate_to_datetime
from datetime import datetime, timedelta

from config import settings
from database import SessionLocal, Lead, Touchpoint, EmailLog, SyncedEmail

LOOKBACK_DAYS = 14


def _decode(value) -> str:
    if not value:
        return ""
    parts = decode_header(value)
    out = []
    for text, charset in parts:
        if isinstance(text, bytes):
            out.append(text.decode(charset or "utf-8", errors="replace"))
        else:
            out.append(text)
    return "".join(out)


def _connect():
    host = getattr(settings, "zoho_imap_host", None) or "imap.zoho.com"
    conn = imaplib.IMAP4_SSL(host, 993)
    conn.login(settings.zoho_email, settings.zoho_app_password)
    return conn


def _process_folder(conn, folder: str, direction: str, db) -> dict:
    """Scan one IMAP folder and log unseen messages. Returns counters."""
    status, _ = conn.select(f'"{folder}"', readonly=True)
    if status != "OK":
        return {"folder": folder, "error": f"cannot open folder {folder}"}

    since = (datetime.utcnow() - timedelta(days=LOOKBACK_DAYS)).strftime("%d-%b-%Y")
    status, data = conn.search(None, f"(SINCE {since})")
    if status != "OK":
        return {"folder": folder, "error": "search failed"}

    logged, matched_leads, already_seen = 0, 0, 0
    for num in data[0].split():
        status, msg_data = conn.fetch(num, "(BODY.PEEK[HEADER])")
        if status != "OK" or not msg_data or msg_data[0] is None:
            continue
        msg = email.message_from_bytes(msg_data[0][1])

        message_id = (msg.get("Message-ID") or "").strip()
        if not message_id:
            continue
        if db.query(SyncedEmail).filter(SyncedEmail.message_id == message_id).first():
            already_seen += 1
            continue

        # The counterparty: To for outbound, From for inbound.
        raw_addr = msg.get("To") if direction == "outbound" else msg.get("From")
        _, addr = parseaddr(raw_addr or "")
        addr = addr.strip().lower()
        subject = _decode(msg.get("Subject"))[:490]
        try:
            msg_date = parsedate_to_datetime(msg.get("Date"))
            if msg_date.tzinfo is not None:
                msg_date = msg_date.astimezone(tz=None).replace(tzinfo=None)
        except Exception:
            msg_date = datetime.utcnow()

        lead = None
        if addr and addr != (settings.zoho_email or "").lower():
            lead = db.query(Lead).filter(Lead.email.ilike(addr)).first()

        record = SyncedEmail(
            message_id=message_id,
            direction=direction,
            lead_id=lead.id if lead else None,
            address=addr,
            subject=subject,
            email_date=msg_date,
        )
        db.add(record)

        if lead:
            matched_leads += 1
            db.add(Touchpoint(
                lead_id=lead.id,
                type="email",
                direction=direction,
                summary=f'{"Sent" if direction == "outbound" else "Reply received"}: {subject}',
                outcome="connected" if direction == "inbound" else None,
            ))
            if direction == "outbound":
                db.add(EmailLog(
                    lead_id=lead.id,
                    to_email=addr,
                    subject=subject,
                    body_preview=f"(sent from Zoho mailbox {settings.zoho_email})",
                    status="sent",
                    sent_at=msg_date,
                ))
                lead.last_contact = msg_date
                if lead.stage == "new":
                    lead.stage = "contacted"
            else:
                # A real human wrote back — that lead is hot.
                lead.temperature = "hot"
            lead.updated_at = datetime.utcnow()

        logged += 1

    db.commit()
    return {"folder": folder, "logged": logged, "matched_leads": matched_leads,
            "already_seen": already_seen}


def sync_zoho_mailbox() -> dict:
    """Scan Sent + Inbox of the Zoho mailbox and log everything new into NOVA."""
    if not (getattr(settings, "zoho_email", None) and getattr(settings, "zoho_app_password", None)):
        return {"status": "skipped", "reason": "ZOHO_EMAIL / ZOHO_APP_PASSWORD not configured"}

    db = SessionLocal()
    try:
        conn = _connect()
    except imaplib.IMAP4.error as e:
        db.close()
        return {"status": "failed", "error": f"IMAP login failed: {e}. "
                "Check ZOHO_APP_PASSWORD is an app-specific password and IMAP is enabled in Zoho."}
    except Exception as e:
        db.close()
        return {"status": "failed", "error": str(e)}

    try:
        results = [
            _process_folder(conn, "Sent", "outbound", db),
            _process_folder(conn, "INBOX", "inbound", db),
        ]
        return {"status": "ok", "results": results}
    except Exception as e:
        db.rollback()
        return {"status": "failed", "error": str(e)}
    finally:
        try:
            conn.logout()
        except Exception:
            pass
        db.close()
