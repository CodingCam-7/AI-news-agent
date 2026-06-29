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
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

COLLECTION = "seen_articles"
RECIPIENTS_COLLECTION = "recipients"

_db_client = None


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
            local_path = os.path.join(os.path.dirname(__file__), "firebase-credentials.json")
            if not os.path.exists(local_path):
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
    doc_id = hashlib.sha256(email.encode()).hexdigest()
    data = {**recipient, "email": email, "active": recipient.get("active", True)}
    db.collection(RECIPIENTS_COLLECTION).document(doc_id).set(data, merge=True)
    logger.info("Saved recipient: %s", email)


def deactivate_recipient(email: str) -> None:
    """Mark a recipient as inactive without deleting their record."""
    db = _db()
    if db is None:
        raise RuntimeError("Firestore is not available.")
    doc_id = hashlib.sha256(email.strip().lower().encode()).hexdigest()
    db.collection(RECIPIENTS_COLLECTION).document(doc_id).set({"active": False}, merge=True)
    logger.info("Deactivated recipient: %s", email)


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
