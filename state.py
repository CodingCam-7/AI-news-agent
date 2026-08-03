"""
state.py — Firebase Firestore client for cross-run deduplication.

Stores the URL of every article included in a sent digest so subsequent runs
skip it. Degrades gracefully when no credentials are present (local dev without
Firebase just re-sends items — expected behaviour during testing).

Credential resolution order:
  1. FIREBASE_CREDENTIALS env var — JSON string (used in CI / GitHub Actions)
  2. firebase-credentials.json file in the project root (local dev)
"""

import hashlib
import json
import logging
import os
import re
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COLLECTION = "seen_articles"
RECIPIENTS_COLLECTION = "recipients"
_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

_db_client = None


def mask_email(email: str | None) -> str:
    """
    Redact an address for logging: 'recipient3@example.com' -> 's***@gmail.com'.

    The digest runs in GitHub Actions, and on a public repository workflow logs
    are world-readable — so a recipient's address must never be written to
    stdout in full. The first character and the domain are kept so you can still
    tell which run belongs to whom; the fixed '***' hides the local part's
    length so the address can't be reconstructed from it.

    Use this for every log line, print, and exception message that touches a
    recipient address. It is not needed for the digest emails themselves.
    """
    if not email:
        return "(no address)"
    local, sep, domain = email.strip().partition("@")
    if not sep or not local:
        return "***"
    return f"{local[0]}***@{domain}"


def _db():
    global _db_client
    if _db_client is not None:
        return _db_client

    try:
        import firebase_admin
        from firebase_admin import credentials, firestore
    except ImportError:
        logger.warning("firebase-admin not installed — deduplication disabled.")
        return None

    if not firebase_admin._apps:
        cred_json = os.environ.get("FIREBASE_CREDENTIALS")
        if cred_json:
            cred = credentials.Certificate(json.loads(cred_json))
        else:
            preferred = os.path.expanduser("~/.config/ai-news-agent/firebase-credentials.json")
            fallback  = os.path.join(os.path.dirname(__file__), "firebase-credentials.json")
            if os.path.exists(preferred):
                local_path = preferred
            elif os.path.exists(fallback):
                local_path = fallback
            else:
                logger.warning("No Firebase credentials found — deduplication disabled.")
                return None
            cred = credentials.Certificate(local_path)
        firebase_admin.initialize_app(cred)

    from firebase_admin import firestore
    _db_client = firestore.client()
    return _db_client


def _doc_id(url: str) -> str:
    return hashlib.sha256(url.encode()).hexdigest()


def load_seen() -> set[str]:
    """Return the set of all article URLs already included in a sent digest."""
    db = _db()
    if db is None:
        return set()
    try:
        return {doc.get("url") for doc in db.collection(COLLECTION).stream() if doc.get("url")}
    except Exception as exc:
        logger.warning("Could not load seen URLs from Firestore: %s", exc)
        return set()


def load_recipients() -> list[dict]:
    """
    Load active recipients from Firestore.
    Falls back to recipients.json for local development without a Firestore connection.
    Raises RuntimeError if neither source is available.
    """
    db = _db()
    if db is not None:
        try:
            docs = [doc.to_dict() for doc in db.collection(RECIPIENTS_COLLECTION).stream()]
            active = [r for r in docs if r.get("active", True)]
            if active:
                return active
        except Exception as exc:
            logger.warning("Could not load recipients from Firestore: %s", exc)

    local_path = os.path.join(os.path.dirname(__file__), "recipients.json")
    if os.path.exists(local_path):
        logger.warning("Falling back to recipients.json — Firestore unavailable or empty.")
        with open(local_path) as f:
            return json.load(f)

    raise RuntimeError(
        "No recipients found. Add recipients to Firestore or create a recipients.json file."
    )


def save_recipient(recipient: dict) -> None:
    """
    Write or update a recipient in Firestore.
    Uses a hash of the email as the document ID so re-saving is idempotent.
    """
    db = _db()
    if db is None:
        raise RuntimeError("Firestore is not available — cannot save recipient.")
    email = recipient.get("email", "").strip().lower()
    if not email:
        raise ValueError("Recipient must have an email address.")
    if not _EMAIL_RE.match(email):
        raise ValueError(f"Invalid email address: {mask_email(email)}")
    doc_id = hashlib.sha256(email.encode()).hexdigest()
    data = {**recipient, "email": email, "active": recipient.get("active", True)}
    db.collection(RECIPIENTS_COLLECTION).document(doc_id).set(data, merge=True)
    logger.info("Saved recipient: %s", mask_email(email))


def set_extra_topics(email: str, topics: list[str]) -> None:
    """
    Set a recipient's person-specific extra topics, replacing any existing list.

    These are topics granted to one person on request rather than offered on the
    Google Form. They live in their own field because sync_recipients.py rewrites
    `topics` from the form on every run — anything added there would be overwritten.
    Pass [] to clear.
    """
    from config import TOPICS

    db = _db()
    if db is None:
        raise RuntimeError("Firestore is not available.")

    unknown = [t for t in topics if t not in TOPICS]
    if unknown:
        raise ValueError(f"Unknown topic(s) not in config.TOPICS: {unknown}")

    doc_id = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    db.collection(RECIPIENTS_COLLECTION).document(doc_id).set(
        {"extra_topics": topics}, merge=True
    )
    logger.info("Set extra topics for %s: %s", mask_email(email), topics or "none")


def set_name_override(email: str, name: str | None) -> None:
    """
    Set the display name used to greet a recipient, overriding the Google Form.

    The form asks for a legal first name; some people would rather be greeted by
    something else. Like `extra_topics`, this lives in its own field because
    sync_recipients.py rewrites `name` from the form on every run — a value
    hand-edited there would be wiped on the next digest. The sync never writes
    `name_override`, and merge=True leaves absent fields untouched, so it
    survives. Pass None to clear.

    It is also why no name↔address mapping is hardcoded in source: this repo is
    public, and that mapping is exactly the kind of personal data that must not
    be published. Set it from a Python shell instead:

        from state import set_name_override
        set_name_override("person@example.com", "Preferred Name")
    """
    db = _db()
    if db is None:
        raise RuntimeError("Firestore is not available.")

    doc_id = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    db.collection(RECIPIENTS_COLLECTION).document(doc_id).set(
        {"name_override": name}, merge=True
    )
    logger.info("Set name override for %s: %s", mask_email(email), name or "cleared")


def load_name_overrides() -> dict[str, str]:
    """
    Return {email: preferred_name} for every recipient that has one set.

    Read in one query so the sync doesn't issue a Firestore round trip per row.
    Returns {} when Firestore is unavailable — the sync then falls back to the
    form-supplied name, which is correct behaviour rather than an error.
    """
    db = _db()
    if db is None:
        return {}
    try:
        overrides: dict[str, str] = {}
        for doc in db.collection(RECIPIENTS_COLLECTION).stream():
            d = doc.to_dict() or {}
            email, override = d.get("email"), d.get("name_override")
            if email and override:
                overrides[email.strip().lower()] = override
        return overrides
    except Exception as exc:
        logger.warning("Could not load name overrides from Firestore: %s", exc)
        return {}


def deactivate_recipient(email: str) -> None:
    """Mark a recipient as inactive without deleting their record."""
    db = _db()
    if db is None:
        raise RuntimeError("Firestore is not available.")
    doc_id = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    db.collection(RECIPIENTS_COLLECTION).document(doc_id).set({"active": False}, merge=True)
    logger.info("Deactivated recipient: %s", mask_email(email))


def mark_seen(urls: list[str]) -> None:
    """Persist URLs so they are skipped on the next run."""
    if not urls:
        return
    db = _db()
    if db is None:
        return
    try:
        batch = db.batch()
        now = datetime.now(timezone.utc)
        for url in urls:
            ref = db.collection(COLLECTION).document(_doc_id(url))
            batch.set(ref, {"url": url, "first_seen": now})
        batch.commit()
        logger.info("Marked %d URL(s) as seen.", len(urls))
    except Exception as exc:
        logger.warning("Could not write seen URLs to Firestore: %s", exc)
