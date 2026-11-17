"""Approval-queue writing, shared by the crew and the demo.
Kept dependency-light (no crewai import) so the demo runs anywhere."""
import json
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = ROOT / "output"


def _write_queue(payload: dict) -> tuple[Path, Path]:
    OUTPUT_DIR.mkdir(exist_ok=True)

    json_path = OUTPUT_DIR / "approval_queue.json"
    json_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    md_lines = [
        "# Approval queue",
        f"_Generated {payload['generated_at']} via {payload['source']}. "
        "Change a post's status to \"approved\" in approval_queue.json "
        "before publishing._",
        "",
    ]
    for item in payload["posts"]:
        md_lines += [f"## Post {item['id']} — {item['status']}", "", item["text"], ""]
        if item.get("image"):
            rel = Path(item["image"]).name
            md_lines += [f"![Post {item['id']} card](images/{rel})",
                         f"_Image: {item['image']} (draft — not published)_", ""]
        package = item.get("video_package")
        if package:
            md_lines += [f"**Video package (Reel):** hook — {package.get('hook', '')}", ""]
            for seg in package.get("captions") or []:
                md_lines.append(f"- Caption: {seg}")
            for scene in package.get("scenes") or []:
                md_lines.append(f"- Scene: {scene}")
            if package.get("youtube_outline"):
                md_lines.append(f"- YouTube outline: {package['youtube_outline']}")
            md_lines.append("")
        if item.get("video"):
            for label, rel_path in item["video"].items():
                md_lines.append(
                    f"- Video ({label}): [{rel_path}](videos/{Path(rel_path).name})")
            md_lines += ["_Videos are drafts — not published._", ""]
    md_path = OUTPUT_DIR / "approval_queue.md"
    md_path.write_text("\n".join(md_lines), encoding="utf-8")
    return md_path, json_path


def save_queue(posts: list[str], source: str) -> tuple[Path, Path]:
    stamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    items = [
        {"id": i + 1, "status": "pending", "text": text}
        for i, text in enumerate(posts)
    ]
    payload = {"generated_at": stamp, "source": source, "posts": items}
    return _write_queue(payload)


def attach_images(images: dict[int, str]) -> tuple[Path, Path]:
    """Record generated image-card paths on the existing queue, keeping
    every other field (status included) exactly as it was."""
    json_path = OUTPUT_DIR / "approval_queue.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    for item in payload["posts"]:
        if item["id"] in images:
            item["image"] = images[item["id"]]
    return _write_queue(payload)


def attach_videos(updates: dict[int, dict]) -> tuple[Path, Path]:
    """Merge video data onto the existing queue: updates maps a post id to
    fields to set on that item ("video" paths and/or "video_package").
    Every other field (status included) is kept exactly as it was."""
    json_path = OUTPUT_DIR / "approval_queue.json"
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    for item in payload["posts"]:
        if item["id"] in updates:
            item.update(updates[item["id"]])
    return _write_queue(payload)
