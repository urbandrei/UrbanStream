import asyncio
import os

from urbanstream.llm_config import (
    BOT_NAME,
    BOT_PERSONALITY,
    LLM_MAX_RESPONSE_TOKENS,
    CHROMA_PERSIST_DIR,
    RAG_TOP_K,
)
from urbanstream.ollama_client import OllamaClient
from urbanstream.rag import RAGStore
from urbanstream.smart_filter import SmartFilter
from urbanstream.moderation import ModerationEngine
from urbanstream.twitch_api import timeout_user
from urbanstream.config import CHANNEL

TWITCH_MSG_LIMIT = 450

SYSTEM_PROMPT = f"""{BOT_PERSONALITY}

You are chatting in a Twitch stream for "{CHANNEL}".
Your name is {BOT_NAME}.

Guidelines:
- Keep responses under {TWITCH_MSG_LIMIT} characters.
- Be conversational and fun. Match the energy of chat.
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
        self._moderation = ModerationEngine(self._ollama)
        self._rag = None
        self._running = False

    async def start(self):
        ok, info = await self._ollama.health_check()
        if not ok:
            print(f"[LLM] Ollama not available: {info}")
            print("[LLM] Assistant disabled — start Ollama and restart the bot.")
            return

        print(f"[LLM] Ollama connected. Models: {info}")

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
            warn_msg = f"@{username} ⚠️ Warning: {reason}" if reason else f"@{username} ⚠️ Please follow chat rules."
            await self._bot.send_chat(warn_msg)

        elif action == "jail":
            await self._bot.jail_user(username)
            if reason:
                await self._bot.send_chat(f"@{username} has been jailed: {reason}")

        elif action == "timeout":
            # Try API timeout first
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
            # Also jail locally
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

            # Build messages
            recent = self._filter.get_recent_context()

            user_content = f"Recent chat:\n{recent}\n"
            if rag_context:
                user_content += f"\nRelevant context:\n{rag_context}\n"
            if user_profile:
                user_content += user_profile + "\n"
            user_content += (
                f"\nThe latest message is from {'the streamer' if is_streamer else username}: \"{text}\"\n"
                f"Trigger: {trigger_reason}. Respond naturally or say SKIP to stay silent."
            )

            messages = [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_content},
            ]

            response = await self._ollama.chat(
                messages, max_tokens=LLM_MAX_RESPONSE_TOKENS
            )
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

    async def stop(self):
        self._running = False
        await self._ollama.close()
