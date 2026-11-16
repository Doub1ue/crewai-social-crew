# CrewAI Social Media Crew

A small team of AI agents that researches, drafts, and queues social media
posts for **one account** — with a human approval step before anything is
published. Built for Anthony (GitHub: Doub1ue) with Muse.

## How it works

```
Researcher  ->  Writer  ->  Editor/Reviewer  ->  Approval queue  ->  (you approve)  ->  Publisher
```

1. **Trend Researcher** — finds timely topics in your niche and angles worth posting about.
2. **Content Writer** — turns the research into short, platform-ready draft posts.
3. **Editor / Reviewer** — checks tone, clarity, and safety; removes anything spammy,
   misleading, or off-brand; writes the survivors into the approval queue.
4. **Approval queue** — drafts land in `output/approval_queue.md` (and `.json`).
   Nothing is published from the queue automatically.
5. **Publisher** (`src/publish.py`) — posts *approved* items to a Facebook Page
   via Meta's official Graph API. It runs in dry-run mode unless you pass
   `--confirm` and have set a Page access token. There is no password-based
   posting anywhere in this project.

## Cost

- CrewAI itself: free and open source.
- The AI model is the only real cost. Free options:
  - **Google Gemini API** — free tier (`GOOGLE_API_KEY`)
  - **Groq** — free tier (`GROQ_API_KEY`)
  - Paid options (OpenAI, Anthropic/Claude, DeepSeek) also work — a single
    account posting daily is typically a few dollars a month.
- Facebook/Instagram posting via Meta's API: free. X (Twitter) is not
  included — its API is effectively paywalled.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in ONE model API key
```

Edit `config.yaml` with your account name, niche/topics, tone, and how many
posts per run you want.

## Run it

```bash
# See it work with no API key at all (sample data, no model calls):
python run.py --demo

# Real run (uses the model/key from .env):
python run.py --topic "your topic or campaign"

# Review what the crew produced:
cat output/approval_queue.md

# Publishing (dry run first — prints what WOULD post, sends nothing):
python src/publish.py
# Real publish of approved items only, after you set META_* in .env:
python src/publish.py --confirm
```

## Approving posts

Open `output/approval_queue.json` and change a post's `"status"` from
`"pending"` to `"approved"` (or delete drafts you don't like). The publisher
only ever touches `"approved"` items, and only with `--confirm`.

## Safety rules baked in

- Draft-and-approve by design — no fully autonomous posting.
- No passwords stored or used; publishing uses official API tokens only.
- `.env` is git-ignored — keys never go into this repo.
- The Editor agent is instructed to reject spam, engagement bait, and
  anything that could get the account flagged.

## Project layout

```
run.py               Entry point (--demo for the no-key sample run)
config.yaml          Your brand: account, niche, tone, cadence
requirements.txt     Python dependencies
.env.example         Template for your keys (copy to .env)
src/
  crew.py            The CrewAI agents, tasks, and crew
  demo.py            No-key demo that produces a sample approval queue
  publish.py         Meta Graph API publisher (dry-run by default)
output/              Generated approval queues (git-ignored contents)
```
