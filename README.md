# CrewAI Social Media Crew

A small team of AI agents that researches, drafts, and queues social media
posts for **one account** — with a human approval step before anything is
published. Built for Anthony (GitHub: Doub1ue) with Muse.

## How it works

```
Researcher  ->  Writer  ->  Editor/Reviewer  ->  Approval queue  ->  (you approve)  ->  Publisher
```

1. **Trend Researcher** — finds timely topics in your niche and angles worth posting about.
   It has a live web-search tool (Tavily), so its angles are grounded in current
   results with source URLs, not just the model's training knowledge.
2. **Content Writer** — turns the research into short, platform-ready draft posts.
3. **Editor / Reviewer** — checks tone, clarity, and safety; removes anything spammy,
   misleading, or off-brand; writes the survivors into the approval queue.
4. **Approval queue** — drafts land in `output/approval_queue.md` (and `.json`).
   Nothing is published from the queue automatically.
5. **Image cards** — after the queue is written, every draft post gets a
   matching branded PNG card (1080×1080) in `output/images/`, drawn with
   [Two.js](https://github.com/jonobr1/two.js) running headless in Node.
   The card shows the post's headline text on the brand background from
   `config.yaml` (`brand:` section), and its path is recorded as `"image"`
   in `approval_queue.json` and shown in the `.md`. Cards are drafts too —
   generating them publishes nothing.
6. **Publisher** (`src/publish.py`) — posts *approved* items to a Facebook Page
   via Meta's official Graph API. It runs in dry-run mode unless you pass
   `--confirm` and have set a Page access token. There is no password-based
   posting anywhere in this project.

## Cost

- CrewAI itself: free and open source.
- The AI model is the only real cost. Free options:
  - **Google Gemini API** — free tier (`GOOGLE_API_KEY`, or the vault-held key
    via the google-gemini connector — no key file needed)
  - **Groq** — free tier (`GROQ_API_KEY`)
  - Paid options (OpenAI, Anthropic/Claude, DeepSeek) also work — a single
    account posting daily is typically a few dollars a month.
- **Model fallback** — when the vault-held OpenRouter key is connected, the
  crew automatically falls back to OpenRouter's free models
  (`openrouter/free`) if the Gemini call fails after its retries.
- **Web search** — Tavily's Researcher plan is free (1,000 searches/month,
  no card) via the vault-held key in the custom.tavily connector.
- Facebook/Instagram posting via Meta's API: free. X (Twitter) is not
  included — its API is effectively paywalled.

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then fill in ONE model API key
npm install            # Node deps for the image-card step (two.js + canvas)
```

Edit `config.yaml` with your account name, niche/topics, tone, and how many
posts per run you want. The `brand:` section of `config.yaml` controls the
image cards: background/text/accent colors, the handle printed on each
card, and the card size. If Node.js or the npm packages are missing, runs
still work — the image step is skipped with a warning.

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
config.yaml          Your brand: account, niche, tone, cadence, card colors
requirements.txt     Python dependencies
package.json         Node dependencies for the image step (two.js, canvas)
.env.example         Template for your keys (copy to .env)
src/
  crew.py            The CrewAI agents, tasks, and crew
  demo.py            No-key demo that produces a sample approval queue
  queue_store.py     Approval-queue writing (shared by crew and demo)
  graphics.py        Runs the Two.js card renderer, records image paths
  publish.py         Meta Graph API publisher (dry-run by default)
  vault_llm.py       Gemini LLM using the vault-held key (surrogate auth)
  vault_openrouter_llm.py  OpenRouter free-model LLM (vault key, fallback)
  fallback_llm.py    Wraps the primary LLM, falls back to OpenRouter
  tavily_tool.py     Tavily web-search tool for the Researcher (vault key)
  tavily_search.py   Plain-function Tavily search helper (non-crew use)
graphics/
  make_card.js       Two.js headless renderer: one PNG card per post
output/              Generated approval queues and images (git-ignored contents)
```
