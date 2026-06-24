"""
emailer.py — Step 4 of the AI News Digest Agent.

Formats the ranked+summarized digest into an HTML+plain-text email and sends
it via Gmail SMTP. Run directly to execute the full pipeline:
fetch → rank → summarize → email.

Required environment variables:
  ANTHROPIC_API_KEY   — for the summarization step
  GMAIL_USER          — Gmail address used as the sender
  GMAIL_APP_PASSWORD  — 16-char App Password (myaccount.google.com/apppasswords)
"""

import logging
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from config import DIGEST_RECIPIENT
from fetcher import fetch_all
from ranker import RankedItem, rank
from summarizer import summarize

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587


def _plain_body(items: list[RankedItem], date_str: str) -> str:
    lines = [
        f"AI News Digest — {date_str}",
        f"{len(items)} matched item(s)",
        "=" * 60,
    ]
    for r in items:
        pub = r.item.published.strftime("%Y-%m-%d") if r.item.published else "no date"
        topics = ", ".join(r.matched_topics)
        lines += [
            "",
            f"[{r.score:.0f}pt] {r.item.title}",
            f"{r.item.source}  |  {pub}  |  {topics}",
            r.item.url,
        ]
        if r.summary:
            lines += ["", r.summary]
    lines += ["", "-" * 60, "Delivered by AI News Agent"]
    return "\n".join(lines)


def _html_body(items: list[RankedItem], date_str: str) -> str:
    item_blocks = []
    for r in items:
        pub = r.item.published.strftime("%Y-%m-%d") if r.item.published else "no date"
        topics = ", ".join(r.matched_topics)
        summary_html = f'<p style="margin:8px 0 0;font-size:15px;line-height:1.65;color:#333;">{r.summary}</p>' if r.summary else ""
        item_blocks.append(f"""
    <div style="margin-bottom:28px;padding-bottom:28px;border-bottom:1px solid #e0e0e0;">
      <h2 style="margin:0 0 4px;font-size:16px;font-weight:600;">
        <a href="{r.item.url}" style="color:#1a0dab;text-decoration:none;">{r.item.title}</a>
      </h2>
      <p style="margin:0;font-size:12px;color:#777;">{r.item.source}&nbsp;&middot;&nbsp;{pub}&nbsp;&middot;&nbsp;{topics}</p>
      {summary_html}
    </div>""")

    body = "\n".join(item_blocks)
    return f"""<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"></head>
<body style="font-family:Georgia,serif;max-width:640px;margin:0 auto;padding:24px 16px;color:#222;background:#fff;">
  <header style="border-bottom:3px solid #222;padding-bottom:12px;margin-bottom:28px;">
    <h1 style="margin:0;font-size:22px;letter-spacing:-0.5px;">AI News Digest</h1>
    <p style="margin:4px 0 0;font-size:13px;color:#666;">{date_str}&nbsp;&middot;&nbsp;{len(items)} item(s)</p>
  </header>
  {body}
  <footer style="margin-top:16px;font-size:11px;color:#aaa;">Delivered by AI News Agent</footer>
</body>
</html>"""


def send_digest(ranked: list[RankedItem]) -> None:
    """Send the digest email for all items with score > 0."""
    scored = [r for r in ranked if r.score > 0]
    if not scored:
        logger.warning("No matched items — skipping email send.")
        return

    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not gmail_user or not gmail_password:
        print(
            "Error: GMAIL_USER and GMAIL_APP_PASSWORD must be set.\n"
            "Generate an App Password at myaccount.google.com/apppasswords.",
            file=sys.stderr,
        )
        sys.exit(1)

    date_str = datetime.now().strftime("%Y-%m-%d")
    subject = f"AI News Digest — {date_str} | {len(scored)} item(s)"

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = DIGEST_RECIPIENT
    msg.attach(MIMEText(_plain_body(scored, date_str), "plain"))
    msg.attach(MIMEText(_html_body(scored, date_str), "html"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_password)
        smtp.sendmail(gmail_user, DIGEST_RECIPIENT, msg.as_string())

    print(f"Digest sent to {DIGEST_RECIPIENT} ({len(scored)} item(s)).")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")

    raw = fetch_all()
    ranked = rank(raw)
    summarize(ranked)
    send_digest(ranked)
