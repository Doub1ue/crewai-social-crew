"""No-key demo: produces a sample approval queue with fixed example posts,
so the whole workflow (queue -> approve -> publisher dry run) can be seen
without any API key or model calls."""
from src.queue_store import save_queue

SAMPLE_POSTS = [
    (
        "Quick question for you: what's the one small task you keep putting "
        "off every week? Naming it is usually the first step to handing it "
        "over. (Sample post — written by the demo, not the crew.)"
    ),
    (
        "Behind the scenes today: turning a messy inbox into a short list of "
        "things that actually need a decision. That's the whole trick — most "
        "of the noise never did. (Sample post.)"
    ),
    (
        "A reminder we give every client: you don't need more hours, you "
        "need fewer open loops. Write them down, pick one, close it. "
        "(Sample post.)"
    ),
]


def run_demo():
    return save_queue(SAMPLE_POSTS, source="demo (no API key used)")
