"""
sync_recipients.py — Reads Google Form responses from the linked Google Sheet
and upserts recipient records into Firestore.

Runs automatically before each digest (see .github/workflows/digest.yml).
Can also be run manually: python sync_recipients.py

Authentication reuses the Firebase service account — no extra credentials needed.
The service account must have Viewer access to the Google Sheet.
"""

import json
import logging
import os
import re
import sys

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

SHEET_ID = os.environ.get(
    "GOOGLE_SHEET_ID",
    "1KBtKbXevYqGHsHgK1434sXRdPKQ5_RTYE_oytl86zHw",
)

# Maps Google Form display names → internal topic keys used in config.py and Firestore.
FORM_TOPIC_MAP: dict[str, str] = {
    "AI chatbots & assistants":        "large language models",
    "AI that sees, hears & creates":   "multimodal AI",
    "AI risks & safety":               "AI safety & alignment",
    "Free & open AI models":           "open source AI",
    "The computers that power AI":     "AI hardware & chips",
    "Running AI at scale":             "AI cloud & infrastructure",
    "AI's cost & energy use":          "AI energy & costs",
    "AI that acts on your behalf":     "AI agents",
    "Tools for building with AI":      "AI tooling",
    "AI & money":                      "AI in finance",
    "AI in medicine & health":         "AI in healthcare",
    "AI art, music & video":           "AI in creative industries",
    "AI robots & self-driving":        "robotics & physical AI",
    "AI in restaurants & hospitality": "AI in hospitality and wine",
    "New AI companies & investment":   "AI startups & funding",
    "How businesses are using AI":     "enterprise AI",
    "AI laws & government rules":      "AI policy",
}

# Google Form column headers — must match the question titles in your form exactly.
COL_NAME  = "What is your first name?"
COL_EMAIL = "What is your email address?"
COL_TOPIC_SECTIONS = [
    "Models & Research",
    "Hardware & Infrastructure",
    "Applications",
    "Business & Society",
]
COL_PRIORITY = [
    "My #1 most important topic is...",
    "My #2 most important topic is...",
    "My #3 most important topic is...",
]


def _sheets_client():
    """Build a gspread client reusing the Firebase service account credentials."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        logger.error("gspread not installed — run: pip install gspread")
        sys.exit(1)

    scopes = ["https://www.googleapis.com/auth/spreadsheets.readonly"]
    cred_json = os.environ.get("FIREBASE_CREDENTIALS")
    if cred_json:
        info = json.loads(cred_json)
    else:
        preferred = os.path.expanduser("~/.config/ai-news-agent/firebase-credentials.json")
        fallback  = os.path.join(os.path.dirname(__file__), "firebase-credentials.json")
        local_path = preferred if os.path.exists(preferred) else fallback
        if not os.path.exists(local_path):
            logger.error(
                "No credentials found — set FIREBASE_CREDENTIALS env var "
                "or place firebase-credentials.json at ~/.config/ai-news-agent/."
            )
            sys.exit(1)
        with open(local_path) as f:
            info = json.load(f)

    creds = Credentials.from_service_account_info(info, scopes=scopes)
    return gspread.authorize(creds)


def _parse_topics(row: dict) -> list[str]:
    """
    Pull selected topics from all four checkbox columns and map to internal keys.
    Google Forms separates multiple checkbox selections with ', '.
    """
    topics: list[str] = []
    for col in COL_TOPIC_SECTIONS:
        cell = row.get(col, "").strip()
        if not cell:
            continue
        for raw in cell.split(", "):
            raw = raw.strip()
            if not raw:
                continue
            internal = FORM_TOPIC_MAP.get(raw)
            if internal:
                if internal not in topics:
                    topics.append(internal)
            else:
                logger.warning("Unrecognised topic in form response: %r — skipping.", raw)
    return topics


def _parse_priority(row: dict) -> list[str]:
    """Extract the respondent's top-3 priority topics and map to internal keys."""
    priority: list[str] = []
    for col in COL_PRIORITY:
        raw = row.get(col, "").strip()
        if not raw:
            continue
        internal = FORM_TOPIC_MAP.get(raw)
        if internal and internal not in priority:
            priority.append(internal)
    return priority


def sync() -> int:
    """
    Pull all form responses and upsert each into Firestore.
    If a person submitted multiple times, only the latest response is used.
    Returns the number of recipients synced.
    """
    from state import save_recipient

    client = _sheets_client()
    try:
        records = client.open_by_key(SHEET_ID).sheet1.get_all_records()
    except Exception as exc:
        logger.error("Could not read Google Sheet: %s", exc)
        sys.exit(1)

    if not records:
        logger.warning("Google Sheet has no responses yet.")
        return 0

    logger.info("%d response(s) found in sheet.", len(records))

    # Keep only the latest submission per email address.
    latest: dict[str, dict] = {}
    for row in records:
        email = row.get(COL_EMAIL, "").strip().lower()
        if not email:
            continue
        if not _EMAIL_RE.match(email):
            logger.warning("Skipping response with invalid email address: %r", email)
            continue
        latest[email] = row

    synced = 0
    for email, row in latest.items():
        name   = row.get(COL_NAME, "").strip() or email
        topics = _parse_topics(row)
        priority = _parse_priority(row)

        if not topics:
            logger.warning("No topics selected for %s — skipping.", email)
            continue

        save_recipient({
            "email":    email,
            "name":     name,
            "topics":   topics,
            "priority": priority,
            "active":   True,
        })
        logger.info(
            "Synced: %s — %d topic(s), priority: %s",
            name, len(topics), priority or "none set",
        )
        synced += 1

    return synced


if __name__ == "__main__":
    n = sync()
    print(f"\nSync complete — {n} recipient(s) updated in Firestore.")
