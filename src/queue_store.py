"""Approval-queue writing, shared by the crew and the demo.
Kept dependency-light (no crewai import) so the demo runs anywhere."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"


def save_queue(posts: list[str], source: str) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    items = [
        {"id": i + 1, "status": "pending", "text": text}
        for i, text in enumerate(posts)
    ]
    payload = {"generated_at": stamp, "source": source, "posts": items}

    json_path = OUTPUT_DIR / "approval_queue.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md_lines = [
        "# Approval queue",
        f"_Generated {stamp} via {source}. "
        "Change a post's status to \"approved\" in approval_queue.json "
        "before publishing._",
        "",
    ]
    for item in items:
        md_lines += [f"## Post {item['id']} — pending", "", item["text"], ""]
    md_path = OUTPUT_DIR / "approval_queue.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return md_path, json_path
