"""Publisher: posts APPROVED queue items to a Facebook Page via Meta's
official Graph API.

Safety defaults:
- Without --confirm it is a dry run: it prints what would post, sends nothing.
- It only ever posts items whose status is "approved" in
  output/approval_queue.json.
- It uses an access token from .env (META_ACCESS_TOKEN + META_PAGE_ID).
  No passwords are used or stored anywhere.
"""
import json
import os
import sys
from pathlib import Path

import requests
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
QUEUE = ROOT / "output" / "approval_queue.json"
GRAPH_VERSION = "v21.0"


def main() -> int:
    confirm = "--confirm" in sys.argv
    load_dotenv(ROOT / ".env")

    if not QUEUE.exists():
        print("No approval queue found. Run `python run.py` first.")
        return 1

    payload = json.loads(QUEUE.read_text(encoding="utf-8"))
    approved = [p for p in payload["posts"] if p["status"] == "approved"]
    if not approved:
        print("No posts marked \"approved\" — nothing to publish.")
        return 0

    page_id = os.getenv("META_PAGE_ID", "")
    token = os.getenv("META_ACCESS_TOKEN", "")

    for post in approved:
        print(f"\n--- Post {post['id']} ---\n{post['text']}")
        if not confirm:
            print("[dry run] Would post this to the Facebook Page.")
            continue
        if not page_id or not token:
            print("[error] META_PAGE_ID / META_ACCESS_TOKEN are not set in .env.")
            return 1
        resp = requests.post(
            f"https://graph.facebook.com/{GRAPH_VERSION}/{page_id}/feed",
            data={"message": post["text"], "access_token": token},
            timeout=30,
        )
        if resp.ok:
            post["status"] = "posted"
            print(f"[posted] Facebook post id: {resp.json().get('id')}")
        else:
            print(f"[failed] {resp.status_code}: {resp.text}")
            return 1

    if confirm:
        QUEUE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
