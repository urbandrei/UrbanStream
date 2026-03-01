import asyncio
import os
import re
from datetime import datetime

from urbanstream.llm_config import (
    BOT_NAME,
    LLM_MAX_RESPONSE_TOKENS,
    CHROMA_PERSIST_DIR,
    RAG_TOP_K,
)
from urbanstream.ollama_client import OllamaClient
from urbanstream.rag import RAGStore
from urbanstream.smart_filter import SmartFilter
from urbanstream.moderation import ModerationEngine
from urbanstream.mod_db import ModerationDB
from urbanstream.twitch_api import timeout_user
from urbanstream.config import CHANNEL

TWITCH_MSG_LIMIT = 450

DEFAULT_PERSONALITY = (
    "You are UrbanBot, a concise and professional Twitch chat assistant. "
    "Keep responses short and direct. No fluff."
)

CONFIDENCE_RE = re.compile(r"^CONFIDENCE:\s*(high|low)\s*$", re.I | re.M)
MOD_QUERY_KEYWORDS = re.compile(r"\b(why|jail|jailed|warn|warned|ban|banned|timeout|timed out|moderat|punish|kick)\b", re.I)


def _load_personality(base_dir):
    path = os.path.join(base_dir, "PERSONALITY.md")
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            text = f.read().strip()
        if text:
            return text
    return DEFAULT_PERSONALITY


def _build_system_prompt(personality):
    return f"""{personality}

You are chatting in a Twitch stream for "{CHANNEL}".
Your name is {BOT_NAME}.

Guidelines:
- Keep responses under {TWITCH_MSG_LIMIT} characters.
- Be direct and useful. Do not ramble.
- Use context from recent chat and knowledge base when relevant.
- If you have nothing useful to add, respond with exactly "SKIP" and nothing else.
- Never reveal that you are an AI or LLM unless directly asked.
- Do not repeat what others have said.
"""


class LLMAssistant:
    def __init__(self, bot, state):
        self._bot = bot
        self._state = state
        self._queue = asyncio.Queue()
        self._ollama = OllamaClient()
        self._filter = SmartFilter()
        self._mod_db = None
        self._moderation = None
        self._rag = None
        self._running = False
        self._system_prompt = ""

    async def start(self):
        ok, info = await self._ollama.health_check()
        if not ok:
            print(f"[LLM] Ollama not available: {info}")
            print("[LLM] Assistant disabled — start Ollama and restart the bot.")
            return

        print(f"[LLM] Ollama connected. Models: {info}")
        print(f"[LLM] Fast: {self._ollama.fast_model} | "
              f"Big: {self._ollama.big_model}")

        # Preload fast model into memory
        print(f"[LLM] Preloading fast model...")
        await self._ollama.preload(self._ollama.fast_model)

        # Load personality
        personality = _load_personality(self._state.base_dir)
        self._system_prompt = _build_system_prompt(personality)
        print(f"[LLM] Personality loaded from PERSONALITY.md")

        # Init moderation DB
        db_path = os.path.join(self._state.base_dir, "moderation.db")
        self._mod_db = ModerationDB(db_path)
        self._moderation = ModerationEngine(self._ollama, self._mod_db)

        # Create sync embed wrapper for RAG
        loop = asyncio.get_event_loop()

        def sync_embed(text):
            future = asyncio.run_coroutine_threadsafe(self._ollama.embed(text), loop)
            return future.result(timeout=30)

        persist_dir = os.path.join(self._state.base_dir, CHROMA_PERSIST_DIR)
        self._rag = await asyncio.to_thread(RAGStore, persist_dir, sync_embed)

        # Load knowledge directory
        knowledge_dir = os.path.join(self._state.base_dir, "knowledge")
        loaded = await asyncio.to_thread(self._rag.load_knowledge_dir, knowledge_dir)
        print(f"[LLM] Loaded {loaded} knowledge documents")

        self._running = True
        asyncio.get_event_loop().create_task(self._process_loop())
        print(f"[LLM] Assistant ready — bot name: {BOT_NAME}")

    async def on_chat_message(self, username, text, msg_id=""):
        if not self._running:
            return
        await self._queue.put({
            "type": "chat",
            "username": username,
            "text": text,
            "msg_id": msg_id,
            "is_streamer": username.lower() == CHANNEL.lower(),
        })

    async def on_voice_transcription(self, text):
        if not self._running:
            return
        await self._queue.put({
            "type": "voice",
            "username": CHANNEL.lower(),
            "text": text,
            "msg_id": "",
            "is_streamer": True,
        })

    async def _process_loop(self):
        while self._running:
            try:
                msg = await self._queue.get()
            except asyncio.CancelledError:
                break

            username = msg["username"]
            text = msg["text"]
            is_streamer = msg["is_streamer"]

            # Record in filter buffer
            self._filter.record_message(username, text, is_streamer)

            # Ingest to RAG (fire-and-forget)
            if self._rag:
                asyncio.get_event_loop().create_task(
                    asyncio.to_thread(
                        self._rag.ingest_chat, username, text, is_streamer
                    )
                )

            # Run moderation and filter decision in parallel
            mod_task = asyncio.create_task(
                self._moderation.evaluate(username, text, is_streamer)
            )
            should, score, reason = self._filter.should_respond(
                username, text, is_streamer
            )

            # Await moderation result
            mod_result = await mod_task
            if mod_result:
                await self._handle_moderation(username, text, mod_result)

            # Generate response if filter says yes
            if should:
                await self._generate_and_respond(username, text, is_streamer, reason)

    async def _handle_moderation(self, username, text, result):
        action = result["action"]
        reason = result.get("reason", "")
        severity = result.get("severity", 0.0)
        print(f"[Mod] {action} for {username} (severity={severity:.2f}): {reason}")

        if action == "warn":
            warn_msg = f"@{username} Warning: {reason}" if reason else f"@{username} Please follow chat rules."
            await self._bot.send_chat(warn_msg)

        elif action == "jail":
            await self._bot.jail_user(username)
            if reason:
                await self._bot.send_chat(f"@{username} has been jailed: {reason}")

        elif action == "timeout":
            user_data = self._state.chatters.get(username, {})
            user_id = user_data.get("user_id", "")
            if user_id:
                await asyncio.to_thread(
                    timeout_user,
                    self._bot._token,
                    self._bot._broadcaster_id,
                    user_id,
                    self._moderation.timeout_duration,
                    reason,
                )
            await self._bot.jail_user(username)

    async def _generate_and_respond(self, username, text, is_streamer, trigger_reason):
        try:
            # Retrieve RAG context
            rag_context = ""
            if self._rag:
                results = await asyncio.to_thread(
                    self._rag.retrieve, text, RAG_TOP_K
                )
                if results:
                    snippets = [r["text"] for r in results[:3]]
                    rag_context = "\n".join(f"- {s}" for s in snippets)

            # Get user profile
            user_profile = ""
            if self._rag:
                profile = await asyncio.to_thread(
                    self._rag.get_user_profile, username
                )
                if profile:
                    user_profile = f"\nAbout {username}: {profile}"

            # Check if streamer is asking about moderation
            mod_context = ""
            if is_streamer and self._mod_db and MOD_QUERY_KEYWORDS.search(text):
                mod_context = await asyncio.to_thread(
                    self._lookup_mod_history, text
                )

            # Build messages
            recent = self._filter.get_recent_context()

            user_content = f"Recent chat:\n{recent}\n"
            if rag_context:
                user_content += f"\nRelevant context:\n{rag_context}\n"
            if mod_context:
                user_content += f"\nModeration records:\n{mod_context}\n"
            if user_profile:
                user_content += user_profile + "\n"
            user_content += (
                f"\nThe latest message is from "
                f"{'the streamer' if is_streamer else username}: \"{text}\"\n"
                f"Trigger: {trigger_reason}. Respond naturally or say SKIP to stay silent."
            )

            messages = [
                {"role": "system", "content": self._system_prompt},
                {"role": "user", "content": user_content},
            ]

            # Step 1: Fast model answers
            response = await self._ollama.chat_fast(
                messages, max_tokens=LLM_MAX_RESPONSE_TOKENS
            )
            response = self._strip_confidence(response)

            # Step 2: Escalate to big model if response is weak
            if self._needs_escalation(response):
                print(f"[LLM] Weak response from fast model, escalating to big model")
                thinking_msg = "Let me think about that a little more."
                await self._bot.send_chat(thinking_msg)
                self._state.speech_queue.put(f"{BOT_NAME} says {thinking_msg}")
                response = await self._ollama.chat_big(
                    messages, max_tokens=LLM_MAX_RESPONSE_TOKENS
                )
                response = self._strip_confidence(response)

            response = response.strip()

            # Check for SKIP
            if response.upper() == "SKIP" or not response:
                print(f"[LLM] Skipped response for: {text[:50]}")
                return

            # Truncate to Twitch limit
            if len(response) > TWITCH_MSG_LIMIT:
                response = response[:TWITCH_MSG_LIMIT - 3] + "..."

            # Send to chat
            await self._bot.send_chat(response)

            # Queue for TTS
            self._state.speech_queue.put(f"{BOT_NAME} says {response}")

            self._filter.mark_responded()
            print(f"[LLM] Responded: {response[:80]}")

        except Exception as e:
            print(f"[LLM] Generation error: {e}")

    def _lookup_mod_history(self, text):
        """Search mod DB for usernames mentioned in the message. Sync — call via to_thread."""
        # Try to find a @username or bare username from chatters
        words = re.findall(r"@?(\w+)", text.lower())
        chatters = set(self._state.chatters.keys()) | self._state.jailed
        lines = []
        seen = set()
        for word in words:
            if word in chatters and word not in seen:
                seen.add(word)
                history = self._mod_db.get_user_history(word, limit=5)
                if history:
                    lines.append(f"History for {word}:")
                    for entry in history:
                        ts = datetime.fromtimestamp(entry["timestamp"]).strftime("%Y-%m-%d %H:%M")
                        lines.append(f"  [{ts}] {entry['final_action']}: {entry['reason']}")
        if not lines:
            # Fall back to most recent actions
            recent = self._mod_db.get_recent(limit=3)
            if recent:
                lines.append("Recent moderation actions:")
                for entry in recent:
                    ts = datetime.fromtimestamp(entry["timestamp"]).strftime("%Y-%m-%d %H:%M")
                    lines.append(f"  [{ts}] {entry['username']} - {entry['final_action']}: {entry['reason']}")
        return "\n".join(lines)

    @staticmethod
    def _strip_confidence(text):
        """Remove any CONFIDENCE: lines the model may have added."""
        return CONFIDENCE_RE.sub("", text).strip()

    @staticmethod
    def _needs_escalation(response):
        """Check if a response is too weak and needs a bigger model."""
        clean = response.strip()
        if not clean:
            return True
        # Too short to be useful (less than 10 chars)
        if len(clean) < 10:
            return True
        # Model just echoed back an instruction or tag
        if clean.upper() in ("CONFIDENCE: LOW", "CONFIDENCE: HIGH", "CONFIDENCE:LOW",
                             "CONFIDENCE:HIGH", "SKIP"):
            return False  # SKIP is intentional, not a failure
        return False

    async def stop(self):
        self._running = False
        if self._mod_db:
            self._mod_db.close()
        await self._ollama.close()
