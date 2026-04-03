import asyncio
import re

import speech_recognition as sr

from urbanstream.helpers import parse_ad_duration


def start_voice_listener(bot, state):
    """Start background voice recognition for chat and ad commands."""
    recognizer = sr.Recognizer()
    mic = sr.Microphone()

    with mic as source:
        print("Calibrating microphone for ambient noise...")
        recognizer.adjust_for_ambient_noise(source, duration=1)

    def send(text):
        print(f"[Voice -> Chat] {text}")
        asyncio.run_coroutine_threadsafe(bot.send_chat(text), bot.loop)

    def voice_callback(recognizer, audio):
        try:
            text = recognizer.recognize_google(audio)
        except (sr.UnknownValueError, sr.RequestError):
            return

        lower = text.lower().strip()

        if lower == "chat on":
            state.voice_chat_active = True
            print("[Voice] Chat transcription ON")
            return
        if lower == "chat off":
            state.voice_chat_active = False
            print("[Voice] Chat transcription OFF")
            return

        if lower == "ads on":
            state.auto_ads_enabled = True
            print("[Voice] Auto ads ON")
            return
        if lower == "ads off":
            state.auto_ads_enabled = False
            print("[Voice] Auto ads OFF")
            return

        if "run" in lower and "ad" in lower:
            duration = parse_ad_duration(lower)
            if duration:
                print(f"[Voice] Running {duration}s ad...")
                asyncio.run_coroutine_threadsafe(
                    bot.run_ad(duration), bot.loop
                )
            return

        if state.llm_enabled:
            if lower == "assistant on":
                print("[Voice] LLM assistant already ON")
                return
            if lower == "assistant off":
                state.llm_enabled = False
                print("[Voice] LLM assistant OFF")
                return

            # Always feed voice to LLM (even when voice-to-chat is off)
            if state.llm_assistant:
                asyncio.run_coroutine_threadsafe(
                    state.llm_assistant.on_voice_transcription(text), bot.loop
                )

        if lower.startswith("jail "):
            name = lower[5:].strip()
            if name:
                print(f"[Voice] Jailing {name}")
                asyncio.run_coroutine_threadsafe(bot.jail_user(name), bot.loop)
            return

        if lower.startswith("free "):
            name = lower[5:].strip()
            if name:
                print(f"[Voice] Freeing {name}")
                asyncio.run_coroutine_threadsafe(bot.unjail_user(name), bot.loop)
            return

        if not state.voice_chat_active:
            return

        sentences = re.split(r'(?<=[.!?])\s*', text.strip())
        for sentence in sentences:
            sentence = sentence.strip()
            if sentence:
                send(sentence)
                if state.tts_translate:
                    state.speech_queue.put(sentence)

    recognizer.listen_in_background(mic, voice_callback)
    print("Voice listener active — say 'chat on/off', 'ads on/off', 'run N seconds/minutes of ads'")
