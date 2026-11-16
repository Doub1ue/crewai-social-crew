"""Image-card generation for queued posts.

After a crew or demo run writes the approval queue, this renders one
branded PNG card per post with Two.js running headless in Node
(graphics/make_card.js, using the `canvas` npm package) and records each
card's path back into approval_queue.json / .md.

Cards are drafts, exactly like the post text: generating them changes no
status and publishes nothing. If Node or the npm dependencies are missing,
this step is skipped with a warning instead of failing the run.
"""
import json
import shutil
import subprocess
from pathlib import Path

import yaml

from src.queue_store import OUTPUT_DIR, attach_images

ROOT = Path(__file__).resolve().parent.parent
IMAGES_DIR = OUTPUT_DIR / "images"
SCRIPT = ROOT / "graphics" / "make_card.js"


def _brand_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh) or {}
    brand = dict(cfg.get("brand") or {})
    account = cfg.get("account") or {}
    brand.setdefault("background_color", "#14213d")
    brand.setdefault("text_color", "#ffffff")
    brand.setdefault("accent_color", "#fca311")
    brand.setdefault("handle", "")
    brand.setdefault("card_width", 1080)
    brand.setdefault("card_height", 1080)
    if account.get("name"):
        brand["account_name"] = account["name"]
    return brand


def add_images_to_queue(json_path: Path) -> int:
    """Generate a PNG card for every post in the queue at json_path.

    Returns how many cards were created (0 when the step was skipped)."""
    node = shutil.which("node")
    if not node:
        print("Image step skipped: Node.js not found on PATH.")
        return 0
    if not (ROOT / "node_modules" / "two.js").exists():
        print("Image step skipped: npm dependencies missing — "
              "run `npm install` in the project root first.")
        return 0

    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    brand = _brand_config()
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)

    cards = [
        {"text": item["text"],
         "output": str(IMAGES_DIR / f"post-{item['id']}.png")}
        for item in payload["posts"]
    ]
    if not cards:
        return 0

    job = {
        "width": brand.pop("card_width"),
        "height": brand.pop("card_height"),
        "brand": brand,
        "cards": cards,
    }
    job_path = OUTPUT_DIR / ".card_job.json"
    job_path.write_text(json.dumps(job), encoding="utf-8")
    try:
        proc = subprocess.run(
            [node, str(SCRIPT), str(job_path)],
            cwd=ROOT, capture_output=True, text=True, timeout=300,
        )
    finally:
        job_path.unlink(missing_ok=True)

    images: dict[int, str] = {}
    for line in proc.stdout.splitlines():
        try:
            result = json.loads(line)
        except json.JSONDecodeError:
            continue
        if result.get("ok") and Path(result["output"]).exists():
            post_id = int(Path(result["output"]).stem.split("-")[1])
            images[post_id] = f"output/images/post-{post_id}.png"
    if proc.returncode != 0 and not images:
        detail = (proc.stderr or proc.stdout).strip().splitlines()
        print("Image step failed: " + (detail[-1] if detail else "unknown error"))
        return 0

    if images:
        attach_images(images)
    return len(images)
