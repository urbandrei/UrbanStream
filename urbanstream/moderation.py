import json
from collections import defaultdict

from urbanstream.llm_config import (
    MOD_ENABLED,
    MOD_WARN_THRESHOLD,
    MOD_JAIL_THRESHOLD,
    MOD_TIMEOUT_THRESHOLD,
    MOD_TIMEOUT_DURATION,
    LLM_MAX_RESPONSE_TOKENS,
)

MOD_PROMPT = """\
You are a Twitch chat moderator. Evaluate the following message for rule violations.

Rules: no spam, no hate speech/slurs, no self-promotion/links without permission, no spoilers, no toxicity/harassment.

Message from "{username}": "{text}"

Respond with ONLY valid JSON (no markdown, no explanation):
{{"violation": true/false, "severity": 0.0-1.0, "reason": "brief reason or empty string"}}

If no violation, use: {{"violation": false, "severity": 0.0, "reason": ""}}
"""


class ModerationEngine:
    def __init__(self, ollama_client):
        self._client = ollama_client
        self._warnings = defaultdict(int)  # username -> warning count

    async def evaluate(self, username, text, is_streamer=False):
        if not MOD_ENABLED:
            return None
        # Never moderate the streamer
        if is_streamer:
            return None

        prompt = MOD_PROMPT.format(username=username, text=text)
        try:
            response = await self._client.generate(
                prompt, max_tokens=LLM_MAX_RESPONSE_TOKENS
            )
            result = self._parse_response(response)
        except Exception as e:
            print(f"[Mod] Evaluation error: {e}")
            return None

        if not result or not result.get("violation"):
            return None

        severity = result.get("severity", 0.0)
        reason = result.get("reason", "")
        action = self._decide_action(username, severity)
        if action:
            return {"action": action, "severity": severity, "reason": reason}
        return None

    def _parse_response(self, response):
        # Try to extract JSON from the response
        text = response.strip()
        # Remove markdown code fences if present
        if text.startswith("```"):
            lines = text.split("\n")
            text = "\n".join(lines[1:-1] if lines[-1].strip() == "```" else lines[1:])
            text = text.strip()
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            # Try to find JSON object in the text
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

        # Escalation based on prior warnings
        if prior >= 3 and severity >= MOD_WARN_THRESHOLD:
            self._warnings[username] += 1
            return "timeout"
        if prior >= 2 and severity >= MOD_WARN_THRESHOLD:
            self._warnings[username] += 1
            return "jail"

        # Severity-based action
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
