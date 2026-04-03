import asyncio
import os
import time

import twitchio
import emoji

from urbanstream.config import (
    CHANNEL, REWARD_ACCENT, REWARD_TRANSLATE, REWARD_BABEL,
    REWARD_AD, REWARD_AD_DURATION,
)
from urbanstream.helpers import username_color, strip_twitch_emotes
from urbanstream.twitch_api import start_commercial, fetch_chatters_who_follow
from urbanstream.overlay_server import start_overlay_server
from urbanstream.voice import start_voice_listener

AD_INTERVAL = 20 * 60   # 20 minutes between auto-ads
AD_BUFFER = 10           # extra seconds after ad before transcription stops


class Bot(twitchio.Client):
    def __init__(self, token, broadcaster_id, state):
        super().__init__(token=token, initial_channels=[CHANNEL])
        self._token = token
        self._broadcaster_id = broadcaster_id
        self._state = state

    async def send_chat(self, text):
        channel = self.get_channel(CHANNEL)
        if channel:
            await channel.send(text)

    async def run_ad(self, duration=60):
        state = self._state
        if state.ad_running:
            print("Ad already running, skipping")
            return

        state.ad_running = True
        ok = await asyncio.to_thread(
            start_commercial, self._token, self._broadcaster_id, duration
        )
        if not ok:
            state.ad_running = False
            return

        print(f"[Ad] Started {duration}s commercial")
        state.speech_queue.put("ad start")
        state.voice_chat_active = True

        await asyncio.sleep(duration + AD_BUFFER)

        state.voice_chat_active = False
        state.speech_queue.put("ad done")
        state.ad_running = False
        print("[Ad] Finished")

    async def auto_ad_loop(self):
        state = self._state
        while True:
            await asyncio.sleep(AD_INTERVAL)
            if state.auto_ads_enabled and not state.ad_running:
                print("[Auto-Ad] Running scheduled 60s ad")
                await self.run_ad(60)

    async def chatter_poll_loop(self):
        state = self._state
        while True:
            try:
                result = await asyncio.to_thread(
                    fetch_chatters_who_follow, self._token, self._broadcaster_id
                )
                state.chatters = result
            except Exception as e:
                print(f"Chatter poll error: {e}")
            await asyncio.sleep(30)

    async def event_ready(self):
        print(f"Connected to #{CHANNEL} — listening for messages...")
        start_overlay_server(self._state)
        start_voice_listener(self, self._state)

        self.loop.create_task(self.auto_ad_loop())
        self.loop.create_task(self.chatter_poll_loop())

        # Initialize LLM assistant (if enabled)
        if self._state.llm_enabled:
            from urbanstream.llm_assistant import LLMAssistant
            self._state.llm_assistant = LLMAssistant(self, self._state)
            self.loop.create_task(self._state.llm_assistant.start())

    # ── Accent / Translate / Babel handlers ─────────────

    async def _handle_accent(self, arg, author):
        state = self._state
        if not arg:
            from urbanstream.tts import LANG_MAP
            display = LANG_MAP.get(state.tts_lang, state.tts_lang)
            await self.send_chat(f"Current accent: {display} ({state.tts_lang})")
            return

        from urbanstream.tts import resolve_lang, LANG_MAP
        import random

        if arg.lower() == "random":
            code, name = random.choice(list(LANG_MAP.items()))
            state.tts_lang = code
            state.tts_babel = False
            await self.send_chat(f"TTS accent changed to {name} ({code})")
            print(f"[TTS] Accent set to {name} ({code})")
            return

        if arg.lower() == "babel":
            state.tts_babel = not state.tts_babel
            status = "ON" if state.tts_babel else "OFF"
            await self.send_chat(f"Babel mode {status} — every message gets a random accent")
            print(f"[TTS] Babel mode {status}")
            return

        force = arg.lower().endswith(" force")
        if force:
            arg = arg[:-6].strip()
        code, name = resolve_lang(arg)
        if not code and force and len(arg) == 2:
            code, name = arg.lower(), arg.lower()
        if code:
            state.tts_lang = code
            state.tts_babel = False
            try:
                from gtts import gTTS
                gTTS(text="test", lang=code)
                display = LANG_MAP.get(code, name)
                await self.send_chat(f"TTS accent changed to {display} ({code})")
                print(f"[TTS] Accent set to {display} ({code})")
            except Exception:
                state.tts_lang = "en"
                await self.send_chat(f"Accent '{code}' failed, reset to english (en)")
                print(f"[TTS] Accent '{code}' failed, reset to en")
        else:
            await self.send_chat(f"Unknown accent: {arg}")

    async def _handle_translate(self, arg):
        state = self._state
        if arg == "on":
            state.tts_translate = True
            await self.send_chat("Translation ON — TTS will translate to current accent language")
        elif arg == "off":
            state.tts_translate = False
            await self.send_chat("Translation OFF — TTS will read text as-is")
        else:
            status = "on" if state.tts_translate else "off"
            await self.send_chat(f"Translation is {status}. Use !translate on/off")

    async def _handle_babel(self, author):
        state = self._state
        state.tts_babel = not state.tts_babel
        status = "ON" if state.tts_babel else "OFF"
        await self.send_chat(f"Babel mode {status} — every message gets a random accent")
        print(f"[TTS] Babel mode {status}")

    # ── Channel point redemption mapping ──────────────

    REWARD_MAP = {k: v for k, v in {
        REWARD_ACCENT: "accent",
        REWARD_TRANSLATE: "translate",
        REWARD_BABEL: "babel",
        REWARD_AD: "ad",
    }.items() if k}

    async def _handle_redeem(self, reward_id, author, text):
        action = self.REWARD_MAP.get(reward_id)
        if not action:
            return False
        display = self._state.nicknames.get(author, author)
        self._state.speech_queue.put(f"{display} redeemed {action}")
        print(f"[Redeem] {author} redeemed {action}: {text}")

        if action == "accent":
            await self._handle_accent(text.strip(), author)
        elif action == "translate":
            arg = text.strip().lower() if text.strip() else ""
            if arg in ("on", "off"):
                await self._handle_translate(arg)
            else:
                # Toggle if no argument
                await self._handle_translate("on" if not self._state.tts_translate else "off")
        elif action == "babel":
            await self._handle_babel(author)
        elif action == "ad":
            asyncio.create_task(self.run_ad(REWARD_AD_DURATION))
        return True

    # ── Message handling ──────────────────────────────

    async def event_message(self, message):
        state = self._state
        if not message.author:
            return
        author = message.author.name.lower()

        # --- Channel point redemptions ---
        reward_id = message.tags.get("custom-reward-id", "")
        if reward_id:
            text = strip_twitch_emotes(message)
            text = emoji.replace_emoji(text, replace="").strip()
            await self._handle_redeem(reward_id, author, text)
            return

        text = strip_twitch_emotes(message)
        text = emoji.replace_emoji(text, replace="").strip()
        if not text:
            return

        if message.echo:
            if author not in state.chatters:
                state.chatters[author] = {"color": username_color(author), "user_id": ""}
            state.chat_bubbles[author] = {"text": text[:150], "time": time.time()}
            return
        is_owner = author == CHANNEL.lower()

        # Announce commands via TTS
        if text.startswith("!"):
            display_name = state.nicknames.get(author, message.author.name)
            state.speech_queue.put(f"{display_name} used {text.split()[0]}")

        if is_owner and text.startswith("!nickname "):
            parts = text.split(None, 2)
            if len(parts) == 3:
                target = parts[1].lower().lstrip("@")
                nick = parts[2]
                state.nicknames[target] = nick
                state.save_nicknames()
                print(f"Nickname set: {target} -> {nick}")
            return

        if is_owner and text.startswith("!tts-speed "):
            try:
                speed = float(text.split(None, 1)[1])
                if 0.1 <= speed <= 10:
                    state.tts_speed = speed
                    print(f"TTS speed set to {state.tts_speed}")
            except ValueError:
                pass
            return

        if text.startswith("!idea "):
            idea = text.split(None, 1)[1].strip()
            if idea:
                idea_path = os.path.join(state.base_dir, "ideas.txt")
                with open(idea_path, "a", encoding="utf-8") as f:
                    f.write(f"{author}: {idea}\n")
                await self.send_chat(f"Idea saved from {author}!")
                print(f"[Idea] {author}: {idea}")
            return

        is_mod = message.author.is_mod if hasattr(message.author, 'is_mod') else False
        can_control = is_owner or is_mod

        if can_control and text.startswith("!translate"):
            arg = text.split(None, 1)[1].strip().lower() if " " in text else ""
            await self._handle_translate(arg)
            return

        if can_control and text.startswith("!accent"):
            arg = text.split(None, 1)[1].strip() if " " in text else ""
            await self._handle_accent(arg, author)
            return

        display_name = state.nicknames.get(author, message.author.name)
        utterance = f"{display_name} says {text}"
        print(utterance)
        state.speech_queue.put(utterance)

        if author not in state.chatters:
            color = message.author.color if message.author.color else username_color(author)
            state.chatters[author] = {"color": color, "user_id": str(message.author.id or "")}
        state.chat_bubbles[author] = {"text": text[:150], "time": time.time()}

        # Feed non-command messages to LLM assistant
        if state.llm_enabled and state.llm_assistant:
            msg_id = message.tags.get("id", "")
            asyncio.create_task(state.llm_assistant.on_chat_message(author, text, msg_id))
