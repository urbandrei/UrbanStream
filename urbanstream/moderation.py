import json
import time
from collections import defaultdict
from datetime import datetime

from urbanstream.llm_config import (
    MOD_ENABLED,
    MOD_WARN_THRESHOLD,
    MOD_JAIL_THRESHOLD,
    MOD_TIMEOUT_THRESHOLD,
    MOD_TIMEOUT_DURATION,
    LLM_MAX_RESPONSE_TOKENS,
)

SCREEN_PROMPT = """\
You are a Twitch chat moderator. Evaluate the following message for rule violations.

Rules: no spam, no hate speech/slurs, no self-promotion/links without permission, no spoilers, no toxicity/harassment.

Message from "{username}": "{text}"

Respond with ONLY valid JSON (no markdown, no explanation):
{{"violation": true/false, "severity": 0.0-1.0, "reason": "brief reason or empty string"}}

If no violation, use: {{"violation": false, "severity": 0.0, "reason": ""}}
"""

REVIEW_PROMPT = """\
You are a senior Twitch chat moderator reviewing a flagged message.

Message from "{username}": "{text}"

A junior moderator flagged this with:
  violation: true, severity: {severity}, reason: "{reason}"

Review this assessment. Is the violation real? Could it be sarcasm, humor, or a false positive?

Respond with ONLY valid JSON (no markdown, no explanation):
{{"violation": true/false, "severity": 0.0-1.0, "reason": "brief reason or empty string"}}
"""


class ModerationEngine:
    def __init__(self, ollama_client, mod_db=None):
        self._client = ollama_client
        self._mod_db = mod_db
        self._warnings = defaultdict(int)  # username -> warning count

    async def evaluate(self, username, text, is_streamer=False):
        if not MOD_ENABLED:
            return None
        if is_streamer:
            return None

        # Step 1: Fast model screens
        fast_result = await self._screen(username, text)
        if not fast_result or not fast_result.get("violation"):
            return None

        # Step 2: Big model reviews
        big_result = await self._review(username, text, fast_result)
        confirmed = big_result and big_result.get("violation", False)

        # Determine final action
        final_action = None
        severity = 0.0
        reason = ""
        if confirmed:
            severity = big_result.get("severity", fast_result.get("severity", 0.0))
            reason = big_result.get("reason", fast_result.get("reason", ""))
            final_action = self._decide_action(username, severity)

        # Step 3: Log to SQLite
        if self._mod_db:
            self._mod_db.log_action(
                username=username,
                message=text,
                fast_result=fast_result,
                big_result=big_result or {},
                final_action=final_action or "none",
                severity=severity,
                reason=reason,
            )

        if final_action:
            return {"action": final_action, "severity": severity, "reason": reason}
        return None

    def _format_history(self, username):
        if not self._mod_db:
            return ""
        history = self._mod_db.get_user_history(username, limit=5)
        if not history:
            return ""
        lines = [f"\nPrior moderation history for {username}:"]
        for entry in history:
            ts = datetime.fromtimestamp(entry["timestamp"]).strftime("%Y-%m-%d %H:%M")
            lines.append(f"- [{ts}] {entry['final_action']}: {entry['reason']}")
        return "\n".join(lines)

    async def _screen(self, username, text):
        history = self._format_history(username)
        prompt = SCREEN_PROMPT.format(username=username, text=text) + history
        try:
            response = await self._client.generate_tiny(
                prompt, max_tokens=LLM_MAX_RESPONSE_TOKENS
            )
            return self._parse_response(response)
        except Exception as e:
            print(f"[Mod] Fast screen error: {e}")
            return None

    async def _review(self, username, text, fast_result):
        prompt = REVIEW_PROMPT.format(
            username=username,
            text=text,
            severity=fast_result.get("severity", 0.0),
            reason=fast_result.get("reason", ""),
        )
        try:
            response = await self._client.generate_big(
                prompt, max_tokens=LLM_MAX_RESPONSE_TOKENS
            )
            return self._parse_response(response)
        except Exception as e:
            print(f"[Mod] Big model review error: {e}")
            return None

    def _parse_response(self, response):
        text = response.strip()
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            start = text.find("{")
            end = text.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    return json.loads(text[start:end])
                except json.JSONDecodeError:
                    pass
            print(f"[Mod] Failed to parse response: {text[:100]}")
            return None

    def _decide_action(self, username, severity):
        prior = self._warnings.get(username, 0)

        if prior >= 3 and severity >= MOD_WARN_THRESHOLD:
            self._warnings[username] += 1
            return "timeout"
        if prior >= 2 and severity >= MOD_WARN_THRESHOLD:
            self._warnings[username] += 1
            return "jail"

        if severity >= MOD_TIMEOUT_THRESHOLD:
            self._warnings[username] += 1
            return "timeout"
        if severity >= MOD_JAIL_THRESHOLD:
            self._warnings[username] += 1
            return "jail"
        if severity >= MOD_WARN_THRESHOLD:
            self._warnings[username] += 1
            return "warn"

        return None

    @property
    def timeout_duration(self):
        return MOD_TIMEOUT_DURATION
