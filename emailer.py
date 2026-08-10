"""
emailer.py — Step 4 of the AI News Digest Agent.

Formats the ranked+summarized digest into a newsletter-style HTML email and
sends a personalised copy to each recipient defined in config.RECIPIENTS.
Run directly to execute the full pipeline: fetch → rank → summarize → email.

Required environment variables:
  ANTHROPIC_API_KEY    — for the summarization step
  GMAIL_USER           — Gmail address used as the sender
  GMAIL_APP_PASSWORD   — 16-char App Password (myaccount.google.com/apppasswords)
  FIREBASE_CREDENTIALS — service-account JSON string (optional; enables dedup)
"""

import html
import logging
import os
import smtplib
import sys
from datetime import datetime
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from urllib.parse import urlparse

from fetcher import fetch_all
from ranker import RankedItem, rank
from state import load_recipients, load_seen, mark_seen, mask_email
from summarizer import overview, summarize

logger = logging.getLogger(__name__)

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Shown in place of the summary when every summarization attempt failed for an
# article. The card keeps its title and link, so the reader can still click
# through or ask about what they missed.
SUMMARY_UNAVAILABLE = "Summary unavailable for this article — reply if you'd like details."

# Hold the whole digest when more than this share of summaries fail. A few
# failures are ordinary (a thin article, a one-off refusal) and the notice above
# covers them; a majority means something systemic — bad API key, wrong model
# name, account issue — and a digest of mostly notices is worse than none.
HOLD_FAILURE_RATIO = 0.5

# Background color per topic — all light enough to read on white, black-outlined in the template.
TOPIC_COLORS: dict[str, str] = {
    # Models & Research
    "large language models":      "#bbf7d0",  # light green
    "multimodal AI":              "#fde68a",  # light yellow
    "AI safety & alignment":      "#fecaca",  # light red
    "open source AI":             "#d9f99d",  # light lime
    "frontier lab releases":      "#ddd6fe",  # light periwinkle
    # Hardware & Infrastructure
    "AI hardware & chips":        "#e9d5ff",  # light purple
    "AI cloud & infrastructure":  "#fed7aa",  # light orange
    "AI energy & costs":          "#a7f3d0",  # light teal
    # Applications
    "AI agents":                  "#bae6fd",  # light blue
    "AI tooling":                 "#a5f3fc",  # cyan
    "AI in finance":              "#fef9c3",  # light yellow
    "AI in healthcare":           "#fbcfe8",  # light pink
    "AI in creative industries":  "#f5d0fe",  # light violet
    "robotics & physical AI":     "#e2e8f0",  # light slate
    "AI in hospitality and wine": "#d1fae5",  # pale green
    # Business & Society
    "AI startups & funding":      "#fef3c7",  # light amber
    "enterprise AI":              "#e0e7ff",  # light indigo
    "AI policy":                  "#c7d2fe",  # soft indigo
    "AI & jobs":                  "#fecdd3",  # light rose
}


def _safe_url(url: str) -> str:
    """Allow only http/https URLs — anything else becomes a safe fallback."""
    try:
        if urlparse(url).scheme in ("http", "https"):
            return url
    except Exception:
        pass
    return "#"


def _all_topics(recipient: dict) -> list[str]:
    """
    Every topic a recipient should receive: their form-selected `topics` plus any
    person-specific `extra_topics`.

    `extra_topics` is a separate field because sync_recipients.py rewrites `topics`
    wholesale from the Google Form on every run — a topic hand-added there would be
    wiped on the next digest. The sync never writes `extra_topics`, and Firestore's
    merge=True leaves absent fields untouched, so extras survive.
    """
    topics = list(recipient.get("topics", []))
    for t in recipient.get("extra_topics") or []:
        if t not in topics:
            topics.append(t)
    return topics


def _ordered_topics(recipient: dict) -> list[str]:
    """Return recipient's topics with priority topics moved to the front."""
    topics: list[str] = _all_topics(recipient)
    priority: list[str] = recipient.get("priority", [])
    priority_set = set(priority)
    topic_set = set(topics)
    return [t for t in priority if t in topic_set] + [t for t in topics if t not in priority_set]


def _group_by_topic(items: list[RankedItem], topics: list[str]) -> dict[str, list[RankedItem]]:
    """Assign each item to the first of the recipient's topics it matched."""
    groups: dict[str, list[RankedItem]] = {t: [] for t in topics}
    for item in items:
        for topic in topics:
            if topic in item.matched_topics:
                groups[topic].append(item)
                break  # each article appears once, under its best-matching topic
    return {t: v for t, v in groups.items() if v}


def _topic_section_html(topic: str, items: list[RankedItem]) -> str:
    color = TOPIC_COLORS.get(topic, "#e5e7eb")
    cards = ""
    for r in items:
        pub = r.item.published.strftime("%b %d, %Y") if r.item.published else "no date"
        source = html.escape(r.item.source)
        title = html.escape(r.item.title)
        summary = html.escape(r.summary) if r.summary else ""
        url = html.escape(_safe_url(r.item.url))
        if summary:
            summary_block = f"""
            <tr><td style="padding:0 20px 14px;">
              <p style="margin:0;font-size:14px;line-height:1.7;color:#333;">{summary}</p>
            </td></tr>"""
        elif r.summary_failed:
            summary_block = f"""
            <tr><td style="padding:0 20px 14px;">
              <p style="margin:0;font-size:13px;line-height:1.7;color:#777;font-style:italic;">
                {html.escape(SUMMARY_UNAVAILABLE)}
              </p>
            </td></tr>"""
        else:
            summary_block = ""
        cards += f"""
        <tr><td style="padding:0 24px 16px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border:2px solid #000;background:#fff;">
            <tr><td style="padding:16px 20px 10px;">
              <p style="margin:0 0 5px;font-size:11px;color:#555;font-weight:600;text-transform:uppercase;letter-spacing:0.5px;">
                {source}&nbsp;&nbsp;&middot;&nbsp;&nbsp;{pub}
              </p>
              <h3 style="margin:0;font-size:16px;font-weight:700;line-height:1.4;">
                <a href="{url}" style="color:#000;text-decoration:none;">{title}</a>
              </h3>
            </td></tr>
            {summary_block}
            <tr><td style="padding:0 20px 16px;">
              <a href="{url}"
                 style="display:inline-block;padding:7px 16px;background:#0284c7;color:#fff;
                        font-size:12px;font-weight:700;text-decoration:none;
                        border:2px solid #000;letter-spacing:0.3px;">
                Read more &rarr;
              </a>
            </td></tr>
          </table>
        </td></tr>"""

    return f"""
        <tr><td style="background:{color};border-top:2px solid #000;border-bottom:2px solid #000;
                       padding:10px 24px;">
          <span style="font-size:10px;font-weight:800;letter-spacing:2px;
                       color:#000;text-transform:uppercase;">{html.escape(topic)}</span>
        </td></tr>
        <tr><td style="padding:20px 0 4px;">{cards}</td></tr>"""


def _brief_html(brief: tuple[str, list[str]] | None) -> str:
    """Render the opening brief. Returns an empty string when no brief was generated."""
    if not brief:
        return ""
    hook, bullets = brief
    items = "".join(
        f"""<tr>
              <td valign="top" style="padding:0 8px 6px 0;font-size:14px;line-height:1.6;color:#000;">&bull;</td>
              <td style="padding:0 0 6px;font-size:14px;line-height:1.6;color:#333;">{html.escape(b)}</td>
            </tr>"""
        for b in bullets
    )
    hook_block = f"""
          <p style="margin:0 0 12px;font-size:15px;line-height:1.6;color:#000;font-weight:700;">
            {html.escape(hook)}
          </p>""" if hook else ""

    # Top and bottom padding are deliberately equal: the brief is a floating card
    # between the header and the first topic banner, and matching gaps keep it
    # centred in that space. An asymmetric value makes it look stuck to whichever
    # edge it is nearer.
    return f"""
        <tr><td style="padding:24px 24px 24px;">
          <table width="100%" cellpadding="0" cellspacing="0"
                 style="border:2px solid #000;background:#dcfce7;">
            <tr><td style="padding:16px 20px 6px;">
              <p style="margin:0 0 10px;font-size:10px;font-weight:800;letter-spacing:2px;
                        color:#166534;text-transform:uppercase;">Today's Brief</p>
              {hook_block}
              <table width="100%" cellpadding="0" cellspacing="0">{items}</table>
            </td></tr>
          </table>
        </td></tr>"""


def _html_body(
    items: list[RankedItem],
    recipient: dict,
    date_str: str,
    brief: tuple[str, list[str]] | None = None,
) -> str:
    name = html.escape(recipient.get("name", ""))
    groups = _group_by_topic(items, _ordered_topics(recipient))
    sections = "".join(_topic_section_html(t, v) for t, v in groups.items())
    n = len(items)
    article_word = "article" if n == 1 else "articles"

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width,initial-scale=1.0">
</head>
<body style="margin:0;padding:0;background:#f0fdf4;font-family:Arial,Helvetica,sans-serif;">
<table width="100%" cellpadding="0" cellspacing="0" style="background:#f0fdf4;">
  <tr><td align="center" style="padding:24px 12px;">
    <table width="600" cellpadding="0" cellspacing="0"
           style="max-width:600px;width:100%;border:2px solid #000;">

      <!-- Header -->
      <tr><td style="background:#14532d;padding:28px 28px 22px;border-bottom:2px solid #000;">
        <h1 style="margin:0 0 8px;color:#fff;font-size:26px;font-weight:800;
                   letter-spacing:-0.5px;">&#129302; AI News Digest</h1>
        <p style="margin:0;color:#86efac;font-size:13px;">
          Hi {name}&nbsp;&nbsp;&middot;&nbsp;&nbsp;{date_str}&nbsp;&nbsp;&middot;&nbsp;&nbsp;{n} {article_word} matched your topics
        </p>
      </td></tr>

      <!-- Opening brief -->
      {_brief_html(brief)}

      <!-- Article sections grouped by topic -->
      {sections}

      <!-- Footer -->
      <tr><td style="background:#dcfce7;border-top:2px solid #000;
                     padding:16px 28px;text-align:center;">
        <p style="margin:0;font-size:11px;color:#166534;">
          AI News Agent &nbsp;&middot;&nbsp; Delivered every 3 days &nbsp;&middot;&nbsp; {date_str}
        </p>
      </td></tr>

    </table>
  </td></tr>
</table>
</body>
</html>"""


def _plain_body(
    items: list[RankedItem],
    recipient: dict,
    date_str: str,
    brief: tuple[str, list[str]] | None = None,
) -> str:
    name = recipient.get("name", "")
    lines = [
        f"AI News Digest — {date_str}",
        f"Hi {name} — {len(items)} article(s) matched your topics",
        "=" * 60,
    ]
    if brief:
        hook, bullets = brief
        lines += ["", "TODAY'S BRIEF"]
        if hook:
            lines += ["", hook]
        lines += [""] + [f"  - {b}" for b in bullets]
        lines += ["", "=" * 60]
    for topic, topic_items in _group_by_topic(items, _ordered_topics(recipient)).items():
        lines += ["", f"── {topic.upper()} ──"]
        for r in topic_items:
            pub = r.item.published.strftime("%Y-%m-%d") if r.item.published else "no date"
            lines += ["", r.item.title, f"{r.item.source} · {pub}", r.item.url]
            if r.summary:
                lines += ["", r.summary]
            elif r.summary_failed:
                lines += ["", f"({SUMMARY_UNAVAILABLE})"]
    lines += ["", "-" * 60, "Delivered by AI News Agent"]
    return "\n".join(lines)


def _send_alert(failures: list[str], attempted: int, held: bool) -> None:
    """
    Email Cameron when summarization failures are detected.

    `held` distinguishes the two outcomes: a held digest went to nobody and needs
    a re-run, whereas a sent digest already reached recipients with an
    "unavailable" notice on the affected articles and needs no action beyond
    knowing why. Either way the failed articles are left unmarked in Firestore,
    so the next scheduled run retries them.
    """
    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    # Default to the sender address so no extra secret is needed in most setups.
    alert_email = os.environ.get("ALERT_EMAIL") or gmail_user
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")

    if dry_run:
        # DRY_RUN promises no SMTP connection at all — print the alert instead.
        print(f"\n[DRY RUN] Would alert {mask_email(alert_email)}: "
              f"{len(failures)}/{attempted} summaries failed, digest "
              f"{'HELD' if held else 'SENT'}.")
        for f in failures:
            print(f"  - {f}")
        return

    if not gmail_user or not gmail_password or not alert_email:
        logger.error("Cannot send failure alert — GMAIL_USER / GMAIL_APP_PASSWORD not set.")
        return

    date_str = datetime.now().strftime("%B %d, %Y")
    n = len(failures)
    tag = "HELD" if held else "SENT"
    subject = f"[ALERT] AI News Digest — {n}/{attempted} summaries failed on {date_str} (digest {tag})"
    failure_lines = "\n".join(f"  - {f}" for f in failures)

    if held:
        outcome = (
            f"{n} of {attempted} article(s) failed summarization — over "
            f"{HOLD_FAILURE_RATIO:.0%} of the digest, which usually means a "
            f"systemic problem rather than a few bad articles.\n"
            f"The digest was NOT sent to recipients.\n\n"
            f"Re-run the workflow with FORCE_SEND=true once the issue is resolved."
        )
    else:
        outcome = (
            f"{n} of {attempted} article(s) failed summarization.\n"
            f"The digest WAS sent — the affected articles appear with their title "
            f"and link, and a note in place of the summary.\n\n"
            f"No action needed unless the same articles keep failing. They were not "
            f"marked as seen, so the next run will retry them."
        )

    plain = (
        f"AI News Digest Alert — {date_str}\n"
        f"{'=' * 60}\n\n"
        f"{outcome}\n\n"
        f"Failed articles:\n{failure_lines}\n\n"
        f"To investigate: check the GitHub Actions logs for WARNING messages.\n"
    )

    msg = MIMEMultipart("alternative")
    msg["Subject"] = subject
    msg["From"] = gmail_user
    msg["To"] = alert_email
    msg.attach(MIMEText(plain, "plain"))

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_password)
        smtp.sendmail(gmail_user, alert_email, msg.as_string())

    if held:
        print(f"[ALERT] Sent to {mask_email(alert_email)}. Digest held — re-run with FORCE_SEND=true once resolved.")
    else:
        print(f"[ALERT] Sent to {mask_email(alert_email)}. Digest still sent with {n} 'summary unavailable' notice(s).")


def send_digest(ranked: list[RankedItem]) -> None:
    """
    Send a personalised newsletter digest to each recipient in Firestore.

    Two safeguards for testing, both read from the environment:
      DRY_RUN=true       — build every digest and print it to the terminal; open no
                           SMTP connection and send nothing. Needs no Gmail creds.
      ONLY_EMAIL=<addr>  — restrict a real send to a single recipient address, so a
                           test send cannot fan out to the whole list.
    """
    dry_run = os.environ.get("DRY_RUN", "").lower() in ("1", "true", "yes")
    only_email = os.environ.get("ONLY_EMAIL", "").strip().lower()

    gmail_user = os.environ.get("GMAIL_USER")
    gmail_password = os.environ.get("GMAIL_APP_PASSWORD")
    if not dry_run and (not gmail_user or not gmail_password):
        print(
            "Error: GMAIL_USER and GMAIL_APP_PASSWORD must be set.\n"
            "Generate an App Password at myaccount.google.com/apppasswords.",
            file=sys.stderr,
        )
        sys.exit(1)

    date_str = datetime.now().strftime("%B %d, %Y")
    scored = [r for r in ranked if r.score > 0]

    if not scored:
        logger.warning("No matched items — skipping email send.")
        return

    recipients = load_recipients()
    if only_email:
        recipients = [r for r in recipients if r["email"].strip().lower() == only_email]
        if not recipients:
            logger.warning("ONLY_EMAIL=%s matched no active recipient — nothing to send.", mask_email(only_email))
            return
        print(f"ONLY_EMAIL set — restricting send to {mask_email(only_email)} ({len(recipients)} recipient).")

    # Build each recipient's article set and opening brief BEFORE opening the SMTP
    # connection — the brief costs an API call per recipient, and holding the SMTP
    # socket open across those calls risks the server timing the connection out.
    outgoing: list[tuple[dict, list[RankedItem], tuple[str, list[str]] | None]] = []
    for recipient in recipients:
        recipient_items = [
            r for r in scored
            if any(t in r.matched_topics for t in _all_topics(recipient))
        ]
        if not recipient_items:
            logger.warning("No matched items for %s — skipping.", mask_email(recipient["email"]))
            continue

        # The brief is a nice-to-have: on failure we drop it and send the digest anyway.
        try:
            brief = overview(recipient_items, recipient)
        except Exception as exc:
            logger.warning("Opening brief failed for %s: %s", mask_email(recipient["email"]), exc)
            brief = None

        outgoing.append((recipient, recipient_items, brief))

    if not outgoing:
        logger.warning("No recipients had matched items — nothing to send.")
        return

    if dry_run:
        for recipient, recipient_items, brief in outgoing:
            print(f"\n{'#' * 70}")
            print(f"# DRY RUN — would send to {mask_email(recipient['email'])} "
                  f"({len(recipient_items)} article(s))")
            print(f"{'#' * 70}")
            print(_plain_body(recipient_items, recipient, date_str, brief))
        print(f"\nDRY_RUN complete — {len(outgoing)} digest(s) built, 0 sent.")
        return

    with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as smtp:
        smtp.ehlo()
        smtp.starttls()
        smtp.login(gmail_user, gmail_password)

        for recipient, recipient_items, brief in outgoing:
            subject = f"AI News Digest — {date_str} | {len(recipient_items)} article(s)"
            msg = MIMEMultipart("alternative")
            msg["Subject"] = subject
            msg["From"] = gmail_user
            msg["To"] = recipient["email"]
            msg.attach(MIMEText(_plain_body(recipient_items, recipient, date_str, brief), "plain"))
            msg.attach(MIMEText(_html_body(recipient_items, recipient, date_str, brief), "html"))

            smtp.sendmail(gmail_user, recipient["email"], msg.as_string())
            print(f"Digest sent to {mask_email(recipient['email'])} ({len(recipient_items)} article(s)).")


# ── entry point ───────────────────────────────────────────────────────────────

if __name__ == "__main__":
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s  %(message)s")

    raw = fetch_all()
    ranked = rank(raw)

    # Filter already-sent items before summarizing to avoid wasting API calls.
    # Set FORCE_SEND=true to bypass dedup (useful for testing).
    force_send = os.environ.get("FORCE_SEND", "").lower() in ("1", "true", "yes")
    if force_send:
        print("FORCE_SEND enabled — bypassing dedup.")
        new_ranked = ranked
    else:
        seen = load_seen()
        new_ranked = [r for r in ranked if r.score == 0 or r.item.url not in seen]
        skipped = len(ranked) - len(new_ranked)
        if skipped:
            print(f"Skipping {skipped} already-sent item(s).")

    new_ranked, failures, attempted = summarize(new_ranked)

    # A minority of failures is survivable: those articles ship with a notice in
    # place of the summary, so nobody loses the rest of the digest over one bad
    # article. A majority points at something systemic, so hold and alert.
    held = bool(failures) and len(failures) > attempted * HOLD_FAILURE_RATIO
    if failures:
        _send_alert(failures, attempted, held)
    # Under DRY_RUN a hold would suppress the very preview being asked for, so
    # note it and carry on to print the digest instead of exiting.
    if held and os.environ.get("DRY_RUN", "").lower() not in ("1", "true", "yes"):
        sys.exit(1)

    send_digest(new_ranked)

    # Persist sent URLs so they're skipped on the next run — except the ones that
    # failed summarization. Leaving those unseen means the next run re-fetches and
    # re-summarizes them, so a transient failure self-heals and the article still
    # reaches people (until it ages out of the LOOKBACK_DAYS window).
    mark_seen([r.item.url for r in new_ranked if r.score > 0 and not r.summary_failed])
