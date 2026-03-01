import re
import time
from collections import deque

from urbanstream.llm_config import (
    BOT_NAME,
    LLM_COOLDOWN_SECONDS,
    LLM_RELEVANCE_THRESHOLD,
    LLM_CONTEXT_WINDOW,
)

QUESTION_MARKERS = re.compile(r"[?]\s*$|^(who|what|when|where|why|how|is|are|can|do|does|will|should)\b", re.I)
STREAM_KEYWORDS = re.compile(r"\b(stream|game|play|song|music|follow|sub|raid|hype|pog|gg|lol|lmao)\b", re.I)
EMOTIONAL_MARKERS = re.compile(r"[!]{2,}|[A-Z]{4,}|\b(love|hate|amazing|terrible|awesome|insane)\b", re.I)


class SmartFilter:
    def __init__(self):
        self.recent_messages = deque(maxlen=LLM_CONTEXT_WINDOW)
        self._last_response_time = 0.0

    def record_message(self, username, text, is_streamer=False):
        self.recent_messages.append({
            "username": username,
            "text": text,
            "is_streamer": is_streamer,
            "time": time.time(),
        })

    def get_recent_context(self, limit=None):
        limit = limit or LLM_CONTEXT_WINDOW
        msgs = list(self.recent_messages)[-limit:]
        return "\n".join(f"{m['username']}: {m['text']}" for m in msgs)

    def _relevance_score(self, text, is_streamer):
        score = 0.0
        if QUESTION_MARKERS.search(text):
            score += 0.3
        if len(text) > 30:
            score += 0.1
        if len(text) > 80:
            score += 0.1
        if STREAM_KEYWORDS.search(text):
            score += 0.15
        if EMOTIONAL_MARKERS.search(text):
            score += 0.1
        # Conversation continuation: recent activity
        recent_count = sum(1 for m in self.recent_messages if time.time() - m["time"] < 60)
        if recent_count >= 5:
            score += 0.15
        if is_streamer:
            score += 0.2
        return min(score, 1.0)

    def should_respond(self, username, text, is_streamer=False):
        bot_lower = BOT_NAME.lower()

        # Always respond to direct mentions (bypass cooldown)
        if bot_lower in text.lower():
            return True, 1.0, "direct_mention"

        # Skip very short or emote-only messages
        stripped = re.sub(r"\s+", "", text)
        if len(stripped) < 5:
            return False, 0.0, "too_short"

        # Check cooldown
        elapsed = time.time() - self._last_response_time
        if elapsed < LLM_COOLDOWN_SECONDS:
            return False, 0.0, "cooldown"

        score = self._relevance_score(text, is_streamer)
        if score >= LLM_RELEVANCE_THRESHOLD:
            return True, score, "relevant"

        return False, score, "low_relevance"

    def mark_responded(self):
        self._last_response_time = time.time()
