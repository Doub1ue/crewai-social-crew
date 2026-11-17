"""Video step: Reel's packages -> finished MP4 files (ffmpeg).

Reel (the crew's Video Producer & Animator) writes a *video package* per
post: a hook-first short-form script, a scene list, burned-in caption
segments, and — when the topic suits — a YouTube long-form outline. This
module turns a package plus the post's branded PNG card into real MP4s:

  output/videos/post-<id>-vertical.mp4    1080x1920  (TikTok / Shorts)
  output/videos/post-<id>-horizontal.mp4  1920x1080  (YouTube)

Render recipe (system ffmpeg, no extra Python dependencies): the square
card is upscaled, given a slow Ken Burns zoom with `zoompan`, padded onto
a brand-navy canvas, and the caption segments are drawn in sequence with
`drawtext` (text passed via temp files, so post text needs no escaping).
The hook leads in the accent color; the account handle closes the video.

If a queue item already carries a `video_package` (written by Reel during
a real crew run), it is used as-is. Otherwise a deterministic package is
derived from the post text, so the demo — and any run — can render video
with no model call. Videos are drafts, exactly like the cards: rendering
publishes nothing, and YouTube/TikTok uploading is NOT wired up (see
README). If ffmpeg is missing, the step is skipped with a warning.
"""
import json
import re
import shutil
import subprocess
import sys
import tempfile
import textwrap
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.graphics import _brand_config
from src.queue_store import OUTPUT_DIR, attach_videos

ROOT = Path(__file__).resolve().parent.parent
VIDEOS_DIR = OUTPUT_DIR / "videos"
IMAGES_DIR = OUTPUT_DIR / "images"

FPS = 30
SECONDS_PER_WORD = 0.42
MIN_SEGMENT_SECONDS = 2.0
MAX_SEGMENT_SECONDS = 5.0
MAX_TOTAL_SECONDS = 32.0

FONT_CANDIDATES = [
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _font() -> str | None:
    for candidate in FONT_CANDIDATES:
        if Path(candidate).exists():
            return candidate
    return None


def _hex(color: str) -> str:
    """'#14213d' -> '0x14213d' for ffmpeg color arguments."""
    return "0x" + color.lstrip("#")


# ---------------------------------------------------------------- packages

def build_package_from_text(text: str, handle: str = "") -> dict:
    """Deterministic video package derived from a post's text (no LLM).

    Same shape Reel produces: hook, caption segments, scenes, and a
    YouTube outline (None — a human/Reel decides when a topic suits a
    long-form video)."""
    clean = " ".join(text.split())
    sentences = [s.strip() for s in re.split(r"(?<=[.!?])\s+", clean) if s.strip()]
    hook = sentences[0] if sentences else clean
    if len(hook) > 60:  # the hook band fits ~3 lines; keep it punchy
        hook = textwrap.shorten(hook, width=60, placeholder="…")

    words = clean.split()
    segments: list[str] = []
    current: list[str] = []
    for word in words:
        current.append(word)
        if len(current) >= 7 or word.endswith((".", "!", "?")):
            segments.append(" ".join(current))
            current = []
    if current:
        segments.append(" ".join(current))
    if len(segments) > 6:  # keep the video tight; fold the tail together
        segments = segments[:5] + [" ".join(segments[5:])]
    if hook and segments and segments[0] == hook:
        segments = segments[1:]

    scenes = ["Opening: hook over the branded card"]
    scenes += [f"Caption beat {i + 1} over the slowly zooming card"
               for i in range(len(segments))]
    scenes.append(f"Closing frame with the {handle or 'account'} handle")
    return {
        "hook": hook,
        "captions": segments,
        "scenes": scenes,
        "youtube_outline": None,
        "source": "derived from post text (no model call)",
    }


# ----------------------------------------------------------------- timing

def _segment_plan(package: dict, handle: str) -> list[tuple[str, float, float, bool]]:
    """[(text, start, end, is_hook)] — hook first, captions in order,
    handle as a short closing card if one is configured."""
    entries: list[tuple[str, bool]] = []
    if package.get("hook"):
        entries.append((package["hook"], True))
    entries += [(seg, False) for seg in package.get("captions") or []]
    if handle:
        entries.append((handle, False))
    if not entries:
        entries = [("", False)]

    durations = [
        min(MAX_SEGMENT_SECONDS,
            max(MIN_SEGMENT_SECONDS, len(text.split()) * SECONDS_PER_WORD))
        for text, _ in entries
    ]
    total = sum(durations)
    if total > MAX_TOTAL_SECONDS:
        scale = MAX_TOTAL_SECONDS / total
        durations = [max(1.6, d * scale) for d in durations]

    plan, t = [], 0.0
    for (text, is_hook), dur in zip(entries, durations):
        plan.append((text, t, t + dur, is_hook))
        t += dur
    return plan


# ----------------------------------------------------------------- render

def _render_one(image: Path, package: dict, brand: dict,
                out_path: Path, vertical: bool, workdir: Path) -> None:
    width, height = (1080, 1920) if vertical else (1920, 1080)
    handle = brand.get("handle", "")
    plan = _segment_plan(package, handle)
    total_seconds = plan[-1][2]
    frames = max(1, round(total_seconds * FPS))
    font = _font()

    filters = [
        "scale=2160:2160:flags=lanczos",
        (f"zoompan=z='min(zoom+0.0005,1.12)':x='iw/2-(iw/zoom/2)'"
         f":y='ih/2-(ih/zoom/2)':d={frames}:s=1080x1080:fps={FPS}"),
    ]
    if vertical:
        filters.append(f"pad=1080:1920:0:420:color={_hex(brand['background_color'])}")
    else:
        filters.append(f"pad=1920:1080:420:0:color={_hex(brand['background_color'])}")

    if font:
        wrap_width = 26 if vertical else 44
        for i, (text, start, end, is_hook) in enumerate(plan):
            if not text:
                continue
            text_file = workdir / f"seg-{i}.txt"
            wrapped = "\n".join(textwrap.wrap(text, width=wrap_width) or [text])
            text_file.write_text(wrapped, encoding="utf-8")
            size = 52 if is_hook else 46
            color = brand["accent_color"] if is_hook else brand["text_color"]
            if vertical:
                y = "150" if is_hook else "1560"
                box = ""
            else:
                y = "h-260" if not is_hook else "120"
                box = ":box=1:boxcolor=black@0.45:boxborderw=24"
            filters.append(
                f"drawtext=fontfile={font}:textfile={text_file}"
                f":fontsize={size}:fontcolor={_hex(color)}"
                f":x=(w-text_w)/2:y={y}:line_spacing=12"
                f":enable='between(t,{start:.2f},{end:.2f})'{box}"
            )

    cmd = [
        "ffmpeg", "-y", "-i", str(image),
        "-vf", ",".join(filters),
        "-c:v", "libx264", "-pix_fmt", "yuv420p", "-r", str(FPS),
        "-movflags", "+faststart", str(out_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=600)
    if proc.returncode != 0 or not out_path.exists():
        detail = (proc.stderr or "").strip().splitlines()
        raise RuntimeError(
            "ffmpeg failed: " + (detail[-1] if detail else "unknown error"))


def render_post_videos(post_id: int, image: Path, package: dict,
                       brand: dict) -> dict:
    """Render both orientations for one post. Returns the queue `video`
    dict with project-relative paths."""
    VIDEOS_DIR.mkdir(parents=True, exist_ok=True)
    outputs = {}
    with tempfile.TemporaryDirectory() as tmp:
        workdir = Path(tmp)
        for label, vertical in (("vertical", True), ("horizontal", False)):
            out_path = VIDEOS_DIR / f"post-{post_id}-{label}.mp4"
            _render_one(image, package, brand, out_path, vertical, workdir)
            outputs[label] = f"output/videos/post-{post_id}-{label}.mp4"
    return outputs


def _fallback_card(post_id: int, brand: dict) -> Path:
    """A plain brand-navy 1080x1080 PNG for posts without a card image."""
    IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    path = IMAGES_DIR / f"post-{post_id}.png"
    if not path.exists():
        subprocess.run(
            ["ffmpeg", "-y", "-f", "lavfi", "-i",
             f"color=c={_hex(brand['background_color'])}:s=1080x1080",
             "-frames:v", "1", str(path)],
            capture_output=True, text=True, timeout=60, check=True)
    return path


# -------------------------------------------------------------- queue step

def add_videos_to_queue(json_path: Path, only_id: int | None = None) -> int:
    """Render MP4s for posts in the queue at json_path and record them.

    Uses each item's existing `video_package` when Reel wrote one;
    otherwise derives a package from the post text. Returns how many
    posts got videos (0 when the step was skipped)."""
    if not shutil.which("ffmpeg"):
        print("Video step skipped: ffmpeg not found on PATH.")
        return 0

    payload = json.loads(Path(json_path).read_text(encoding="utf-8"))
    brand = _brand_config()
    updates: dict[int, dict] = {}
    for item in payload["posts"]:
        if only_id is not None and item["id"] != only_id:
            continue
        package = item.get("video_package") or build_package_from_text(
            item["text"], brand.get("handle", ""))
        image = ROOT / item["image"] if item.get("image") else None
        if image is None or not image.exists():
            image = _fallback_card(item["id"], brand)
        try:
            videos = render_post_videos(item["id"], image, package, brand)
        except Exception as exc:  # noqa: BLE001 — one bad post loses no queue
            print(f"Video render failed for post {item['id']}: {exc}")
            continue
        update = {"video": videos}
        if not item.get("video_package"):
            update["video_package"] = package
        updates[item["id"]] = update

    if updates:
        attach_videos(updates)
    return len(updates)


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description="Render draft videos for the current approval queue")
    parser.add_argument("--post", type=int, default=None,
                        help="only render this post id")
    args = parser.parse_args()
    queue_json = OUTPUT_DIR / "approval_queue.json"
    if not queue_json.exists():
        print("No approval queue found — run `python run.py --demo` first.")
        sys.exit(1)
    made = add_videos_to_queue(queue_json, only_id=args.post)
    print(f"Rendered videos for {made} post(s) into output/videos/.")
