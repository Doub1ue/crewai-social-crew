#!/usr/bin/env python3
"""Entry point.

Usage:
  python run.py --demo              # sample queue, no API key needed
  python run.py                     # real crew run (needs a model key in .env)
  python run.py --topic "launch"    # real run focused on one topic
"""
import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv(ROOT / ".env")

MODEL_KEYS = [
    "GOOGLE_API_KEY",
    "GROQ_API_KEY",
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "DEEPSEEK_API_KEY",
]


def _vault_key_available() -> bool:
    """True when the vault-held Gemini key (google-gemini connector) exists."""
    try:
        sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
        from dynamic_credentials import dynamic_credential_entry
        dynamic_credential_entry("custom.google-gemini")
        return True
    except Exception:
        return False


def main() -> int:
    parser = argparse.ArgumentParser(description="CrewAI social media crew")
    parser.add_argument("--demo", action="store_true",
                        help="produce a sample approval queue without any API key")
    parser.add_argument("--topic", default=None,
                        help="focus the crew on one topic or campaign")
    args = parser.parse_args()

    if args.demo:
        from src.demo import run_demo
        md_path, json_path = run_demo()
    else:
        import os
        if not any(os.getenv(k) for k in MODEL_KEYS) and not _vault_key_available():
            print(
                "No model API key found in .env and no vault Gemini key.\n"
                "Copy .env.example to .env and add ONE key (Gemini and Groq "
                "have free tiers), connect the google-gemini connector, or "
                "run `python run.py --demo` to see the workflow without a key."
            )
            return 1
        from src.crew import run
        md_path, json_path = run(args.topic)

    print(f"\nApproval queue written:\n  {md_path}\n  {json_path}")

    # Draft image cards for the queued posts (Two.js headless via Node).
    # Fail-soft: a graphics problem never loses the queue itself.
    try:
        from src.graphics import add_images_to_queue
        made = add_images_to_queue(json_path)
        if made:
            print(f"Generated {made} draft image card(s) in output/images/ "
                  "(paths recorded in the queue).")
    except Exception as exc:  # noqa: BLE001
        print(f"Image step skipped: {exc}")

    print("Review the drafts, set the good ones to \"approved\" in the JSON, "
          "then run: python src/publish.py   (dry run) ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
