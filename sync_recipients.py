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
import smtplib
import sys
from email.mime.text import MIMEText

logging.basicConfig(level=logging.INFO, format="%(levelname)s  %(message)s")
logger = logging.getLogger(__name__)

_EMAIL_RE = re.compile(r'^[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}$')

SHEET_ID = os.environ.get(
    "GOOGLE_SHEET_ID",
    "GOOGLE_SHEET_ID_REMOVED",
)

# Maps Google Form display names → internal topic keys used in config.py and Firestore.
FORM_TOPIC_MAP: dict[str, str] = {
    "AI chatbots & assistants":        "large language models",
    "AI that sees, hears & creates":   "multimodal AI",
    "AI risks & safety":               "AI safety & alignment",
    "Free & open AI models":           "open source AI",
    "What the big AI labs just shipped": "frontier lab releases",
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
    "AI replacing human jobs":         "AI & jobs",
}

# Google Form column headers.
# Matched by prefix, not equality — Google Sheets includes any help text the question
# carries (e.g. "What is your email address?\n(This is the address ...)") in the header.
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
COL_ADDITIONAL = "Additional topic/s"

# Greeting names that win over whatever the form says, keyed by email.
# The form asks for a legal first name; these are the names those people actually
# want to be greeted by in their digest.
NAME_OVERRIDES: dict[str, str] = {
    "recipient1@example.com": "Paps",
}

OWNER_EMAIL = "owner@example.com"
SMTP_HOST   = "smtp.gmail.com"
SMTP_PORT   = 587


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


def _cell(row: dict, header: str) -> str:
    """
    Look up a column by header prefix.

    Google Sheets folds a question's help text into the header, so the stored header
    is often longer than the question title (e.g. the email question carries
    "\\n(This is the address your digest will be sent to)"). Exact lookup misses those.
    """
    for key, value in row.items():
        if key.startswith(header):
            return str(value).strip()
    return ""


# Strips the option numbering the priority dropdowns carry, e.g. "9. Tools for..." → "Tools for...".
_PRIORITY_PREFIX_RE = re.compile(r"^\s*\d+\.\s*")


def _match_label(text: str) -> str | None:
    """
    Map one form option to its internal topic key.

    Options render as "<label> (<description>)", so the label is a prefix rather than
    the whole string. Labels are mutually non-overlapping, so longest-prefix wins.
    """
    for label in sorted(FORM_TOPIC_MAP, key=len, reverse=True):
        if text.startswith(label):
            return FORM_TOPIC_MAP[label]
    return None


def _parse_topics(row: dict) -> list[str]:
    """
    Pull selected topics from all four checkbox columns and map to internal keys.

    Google Forms joins multiple checkbox selections with ', ' — but each option's
    parenthetical description contains ', ' too, so the cell cannot simply be split.
    Instead each known label is matched where it starts the cell or follows a ', '.
    """
    topics: list[str] = []
    for col in COL_TOPIC_SECTIONS:
        cell = _cell(row, col)
        if not cell:
            continue
        matched = 0
        for label, internal in FORM_TOPIC_MAP.items():
            for m in re.finditer(re.escape(label), cell):
                if m.start() == 0 or cell[m.start() - 2:m.start()] == ", ":
                    matched += 1
                    if internal not in topics:
                        topics.append(internal)
                    break
        if not matched:
            logger.warning("No recognised topics in %r column: %r", col, cell[:120])
    return topics


def _parse_priority(row: dict) -> list[str]:
    """Extract the respondent's top-3 priority topics and map to internal keys."""
    priority: list[str] = []
    for col in COL_PRIORITY:
        raw = _cell(row, col)
        if not raw:
            continue
        internal = _match_label(_PRIORITY_PREFIX_RE.sub("", raw))
        if internal:
            if internal not in priority:
                priority.append(internal)
        else:
            logger.warning("Unrecognised priority pick: %r — skipping.", raw)
    return priority


def _notify_additional_topic(respondent_name: str, respondent_email: str, text: str) -> None:
    """Email the owner when a respondent suggests an additional topic."""
    gmail_user     = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_password:
        logger.warning("GMAIL_USER / GMAIL_APP_PASSWORD not set — cannot send additional-topic notification.")
        return

    subject = f"New topic suggestion from {respondent_name}"
    body = (
        f"{respondent_name} ({respondent_email}) suggested an additional topic:\n\n"
        f"{text}\n\n"
        "Reply to this email or open Claude Code to discuss adding it."
    )
    msg = MIMEText(body, "plain")
    msg["Subject"] = subject
    msg["From"]    = gmail_user
    msg["To"]      = OWNER_EMAIL

    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
            smtp.ehlo()
            smtp.starttls()
            smtp.login(gmail_user, gmail_password)
            smtp.sendmail(gmail_user, OWNER_EMAIL, msg.as_string())
        logger.info("Sent additional-topic notification for %s.", respondent_email)
    except Exception as exc:
        logger.warning("Failed to send additional-topic notification: %s", exc)


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
        email = _cell(row, COL_EMAIL).lower()
        if not email:
            logger.warning("Skipping response with no email address (row: %r).", _cell(row, COL_NAME) or "unnamed")
            continue
        if not _EMAIL_RE.match(email):
            logger.warning("Skipping response with invalid email address: %r", email)
            continue
        latest[email] = row

    synced = 0
    for email, row in latest.items():
        name   = NAME_OVERRIDES.get(email) or _cell(row, COL_NAME) or email
        topics = _parse_topics(row)
        priority = _parse_priority(row)

        # A priority pick implies interest — add it to topics if not already selected.
        for p in priority:
            if p not in topics:
                topics.append(p)
                logger.info("Added priority topic %r to interests for %s.", p, email)

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

        additional = _cell(row, COL_ADDITIONAL)
        if additional:
            _notify_additional_topic(name, email, additional)

        synced += 1

    return synced


if __name__ == "__main__":
    n = sync()
    print(f"\nSync complete — {n} recipient(s) updated in Firestore.")
