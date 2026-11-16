"""CrewAI social media crew: Researcher -> Writer -> Editor -> approval queue.

Nothing in this module publishes anything. The crew's only output is a
draft approval queue in output/approval_queue.md / .json, which a human
reviews before the separate publisher (publish.py) may post approved items.
"""
import os
from pathlib import Path

import yaml
from crewai import Agent, Crew, LLM, Process, Task

from src.queue_store import save_queue

ROOT = Path(__file__).resolve().parent.parent


def load_config() -> dict:
    with open(ROOT / "config.yaml", "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)["account"]


def _sanitize_no_proxy() -> None:
    """httpx (used by the google-genai client) crashes parsing IPv6 entries
    like [::1] in NO_PROXY. Drop colon/bracket entries for this process;
    the egress proxy is still used for external hosts like Google."""
    for var in ("NO_PROXY", "no_proxy"):
        raw = os.getenv(var)
        if raw:
            kept = [e.strip() for e in raw.split(",")
                    if e.strip() and ":" not in e and "[" not in e]
            os.environ[var] = ",".join(kept)


def _vault_gemini_surrogate() -> str | None:
    """Fetch the hsurr:* surrogate for the vault-held Gemini key, if the
    google-gemini connector is set up. The surrogate is not the real key:
    it is swapped for the real key on approved egress to Google, so the
    real key never touches this process, a file, or an env var."""
    try:
        import sys
        sys.path.insert(0, "/opt/muse/skills/custom-connector-setup/bin")
        from dynamic_credentials import dynamic_credential_entry
        entry = dynamic_credential_entry("custom.google-gemini")
        return str(entry["surrogate"])
    except Exception:
        return None


def build_llm():
    """Model from .env (MODEL_NAME).

    Gemini keys, in order: GOOGLE_API_KEY from .env (native provider), or
    the vault-held key via the google-gemini connector (VaultGeminiLLM —
    the real key never leaves secure storage). Other providers use
    CrewAI's native routing with their key from the environment."""
    model = os.getenv("MODEL_NAME", "gemini/gemini-3.5-flash-lite")
    _sanitize_no_proxy()
    if model.startswith("gemini/") and not os.getenv("GOOGLE_API_KEY"):
        if _vault_gemini_surrogate():
            from src.vault_llm import VaultGeminiLLM
            return VaultGeminiLLM(
                model=model.split("/", 1)[1], temperature=0.7
            )
    return LLM(model=model, temperature=0.7)


def build_crew(topic: str | None = None) -> Crew:
    cfg = load_config()
    llm = build_llm()
    focus = topic or ", ".join(cfg.get("topics", [])) or cfg["niche"]

    researcher = Agent(
        role="Social Media Trend Researcher",
        goal=(
            f"Find timely, specific topics and angles in the niche "
            f"'{cfg['niche']}' that the account '{cfg['name']}' could post "
            f"about today, focused on: {focus}."
        ),
        backstory=(
            "You track what people in this niche are actually talking about. "
            "You favor concrete, useful angles over generic motivational filler, "
            "and you never invent statistics, news, or quotes."
        ),
        llm=llm,
        allow_delegation=False,
    )

    writer = Agent(
        role="Social Media Content Writer",
        goal=(
            f"Write {cfg['posts_per_run']} short, platform-ready draft posts "
            f"for {cfg['platform']} in this tone: {cfg['tone']}. "
            f"Use at most {cfg['hashtag_limit']} hashtags per post."
        ),
        backstory=(
            "You write like a helpful human, not a marketing bot: plain words, "
            "one clear idea per post, no engagement bait, no fake urgency, "
            "no promising results you cannot back up."
        ),
        llm=llm,
        allow_delegation=False,
    )

    editor = Agent(
        role="Editor and Safety Reviewer",
        goal=(
            "Review every draft: fix tone and clarity, and REJECT anything "
            "spammy, misleading, off-brand, or likely to get the account "
            "flagged. Output only the surviving drafts in the required format."
        ),
        backstory=(
            "You are the last line of defense for the account's reputation. "
            "When in doubt, you cut the post. You know platform rules punish "
            "spam and inauthentic behavior, so every post must read as genuine."
        ),
        llm=llm,
        allow_delegation=False,
    )

    research_task = Task(
        description=(
            f"Research posting angles for '{cfg['name']}' ({cfg['platform']}) "
            f"in the niche '{cfg['niche']}', focused on: {focus}. "
            "Return 5-7 angles, each with: a one-line hook, why it matters to "
            "the audience today, and one concrete fact or example to build on. "
            "Do not invent news or statistics; mark anything uncertain as an "
            "opinion angle instead."
        ),
        expected_output="A list of 5-7 post angles with hook, audience value, and supporting point.",
        agent=researcher,
    )

    writing_task = Task(
        description=(
            f"Using the research, write exactly {cfg['posts_per_run']} draft "
            f"posts for {cfg['platform']}. Each post: under 100 words, one "
            f"idea, tone = {cfg['tone']}, at most {cfg['hashtag_limit']} "
            "hashtags. Number the posts. No links unless the research "
            "provided a real one."
        ),
        expected_output=f"{cfg['posts_per_run']} numbered draft posts, each under 100 words.",
        agent=writer,
        context=[research_task],
    )

    editing_task = Task(
        description=(
            "Review the drafts. Fix wording where needed. Drop any draft that "
            "is spammy, misleading, off-tone, or repetitive. For each surviving "
            "post, output it in EXACTLY this format, nothing else:\n\n"
            "POST\n<final post text>\nENDPOST"
        ),
        expected_output="One POST...ENDPOST block per approved draft.",
        agent=editor,
        context=[writing_task],
    )

    return Crew(
        agents=[researcher, writer, editor],
        tasks=[research_task, writing_task, editing_task],
        process=Process.sequential,
        verbose=True,
    )


def parse_posts(text: str) -> list[str]:
    posts, current = [], None
    for line in text.splitlines():
        if line.strip() == "POST":
            current = []
        elif line.strip() == "ENDPOST" and current is not None:
            posts.append("\n".join(current).strip())
            current = None
        elif current is not None:
            current.append(line)
    return [p for p in posts if p]


def run(topic: str | None = None) -> tuple[Path, Path]:
    result = build_crew(topic).kickoff()
    posts = parse_posts(str(result))
    if not posts:
        raise RuntimeError(
            "The crew finished but produced no POST blocks. "
            "Re-run, or check the model output above."
        )
    return save_queue(posts, source=f"crewai:{os.getenv('MODEL_NAME', 'default')}")
