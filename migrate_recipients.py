"""
migrate_recipients.py — one-time migration of recipients.json into Firestore.

Run once locally after setting up Firebase credentials:
    python migrate_recipients.py

Safe to re-run — save_recipient() uses merge=True so existing records are updated,
not duplicated.
"""

import json
import os
import sys

from state import save_recipient


def main():
    local_path = os.path.join(os.path.dirname(__file__), "recipients.json")
    if not os.path.exists(local_path):
        print("recipients.json not found — nothing to migrate.", file=sys.stderr)
        sys.exit(1)

    with open(local_path) as f:
        recipients = json.load(f)

    print(f"Migrating {len(recipients)} recipient(s) to Firestore...\n")
    for r in recipients:
        save_recipient(r)
        print(f"  Migrated: {r.get('name')} <{r.get('email')}>")

    print(f"\nDone. {len(recipients)} recipient(s) are now in the Firestore 'recipients' collection.")
    print("You can verify them in the Firebase console and safely delete recipients.json.")


if __name__ == "__main__":
    main()
