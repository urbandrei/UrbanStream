import asyncio
import time

import twitchio
import emoji

from urbanstream.config import CHANNEL
from urbanstream.helpers import username_color, strip_twitch_emotes, find_closest_user
from urbanstream.twitch_api import start_commercial, fetch_chatters_who_follow, delete_message
from urbanstream.overlay_server import start_overlay_server
from urbanstream.voice import start_voice_listener
from urbanstream.llm_assistant import LLMAssistant

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

    async def jail_user(self, target_name):
        state = self._state
        user = find_closest_user(target_name, state.chatters, state.nicknames)
        if not user:
            print(f"[Jail] No match for '{target_name}'")
            return
        state.jailed.add(user)
        display = state.nicknames.get(user, user)
        state.speech_queue.put(f"{display} jailed")
        print(f"[Jail] {user} jailed")

    async def unjail_user(self, target_name):
        state = self._state
        user = find_closest_user(target_name, state.chatters, state.nicknames)
        if not user:
            print(f"[Unjail] No match for '{target_name}'")
            return
        state.jailed.discard(user)
        display = state.nicknames.get(user, user)
        state.speech_queue.put(f"{display} unjailed")
        print(f"[Unjail] {user} unjailed")

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

        # Initialize LLM assistant
        self._state.llm_assistant = LLMAssistant(self, self._state)
        self.loop.create_task(self._state.llm_assistant.start())

    async def event_message(self, message):
        state = self._state
        if not message.author:
            return
        author = message.author.name.lower()

        # --- Jailed message filtering ---
        if not message.echo and author in state.jailed:
            clean = strip_twitch_emotes(message)
            clean = emoji.replace_emoji(clean, replace="").strip()
            if clean:
                # Non-emote/emoji text — delete the message
                msg_id = message.tags.get("id", "")
                if msg_id:
                    await asyncio.to_thread(
                        delete_message, self._token, self._broadcaster_id, msg_id
                    )
                print(f"[Jail] Deleted message from {author}: {message.content}")
                return
            # Emote/emoji only — show bubble but skip TTS
            if author not in state.chatters:
                color = message.author.color if message.author.color else username_color(author)
                state.chatters[author] = {"color": color, "user_id": str(message.author.id or "")}
            state.chat_bubbles[author] = {"text": message.content[:150], "time": time.time()}
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

        # --- Jail / Unjail commands ---
        is_mod = message.author.is_mod if hasattr(message.author, 'is_mod') else False
        can_jail = is_owner or is_mod

        if can_jail and text.startswith("!jail "):
            target = text.split(None, 1)[1].strip()
            if target:
                await self.jail_user(target)
            return

        if can_jail and text.startswith("!free "):
            target = text.split(None, 1)[1].strip()
            if target:
                await self.unjail_user(target)
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
        if state.llm_assistant and state.llm_enabled:
            msg_id = message.tags.get("id", "")
            asyncio.create_task(state.llm_assistant.on_chat_message(author, text, msg_id))
