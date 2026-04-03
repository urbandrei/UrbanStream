import difflib
import os
import random
import tempfile
import threading
import time

from gtts import gTTS
import pygame

LANG_MAP = {
    "af": "afrikaans", "ar": "arabic", "bg": "bulgarian", "bn": "bengali",
    "bs": "bosnian", "ca": "catalan", "cs": "czech", "da": "danish",
    "de": "german", "el": "greek", "en": "english", "es": "spanish",
    "et": "estonian", "fi": "finnish", "fr": "french", "gu": "gujarati",
    "hi": "hindi", "hr": "croatian", "hu": "hungarian", "id": "indonesian",
    "is": "icelandic", "it": "italian", "ja": "japanese", "jw": "javanese",
    "kn": "kannada", "ko": "korean", "la": "latin", "lv": "latvian",
    "mk": "macedonian", "ml": "malayalam", "mr": "marathi", "ms": "malay",
    "my": "myanmar", "ne": "nepali", "nl": "dutch", "no": "norwegian",
    "pl": "polish", "pt": "portuguese", "ro": "romanian", "ru": "russian",
    "si": "sinhala", "sk": "slovak", "sq": "albanian", "sr": "serbian",
    "su": "sundanese", "sv": "swedish", "sw": "swahili", "ta": "tamil",
    "te": "telugu", "th": "thai", "tl": "filipino", "tr": "turkish",
    "uk": "ukrainian", "ur": "urdu", "vi": "vietnamese", "zh": "chinese",
}

LANG_NAME_TO_CODE = {name: code for code, name in LANG_MAP.items()}


def resolve_lang(value):
    """Resolve a language code or name to a gTTS language code. Returns (code, name) or (None, None)."""
    value = value.lower().strip()
    if value in LANG_MAP:
        return value, LANG_MAP[value]
    if value in LANG_NAME_TO_CODE:
        return LANG_NAME_TO_CODE[value], value
    matches = difflib.get_close_matches(value, LANG_NAME_TO_CODE.keys(), n=1, cutoff=0.6)
    if matches:
        name = matches[0]
        return LANG_NAME_TO_CODE[name], name
    return None, None


def start_tts_worker(state):
    """Start the TTS background thread consuming from state.speech_queue."""
    def worker():
        pygame.mixer.init()
        while True:
            text = state.speech_queue.get()
            try:
                lang = state.tts_lang
                if state.tts_babel:
                    lang = random.choice(list(LANG_MAP.keys()))
                if state.tts_translate and lang != "en":
                    try:
                        from deep_translator import GoogleTranslator
                        text = GoogleTranslator(source="auto", target=lang).translate(text)
                    except Exception as e:
                        print(f"[TTS] Translation error: {e}")
                tts = gTTS(text=text, lang=lang)
                with tempfile.NamedTemporaryFile(delete=False, suffix=".mp3") as f:
                    temp_path = f.name
                tts.save(temp_path)
                pygame.mixer.music.load(temp_path)
                pygame.mixer.music.play()
                while pygame.mixer.music.get_busy():
                    time.sleep(0.1)
                pygame.mixer.music.unload()
                os.unlink(temp_path)
            except Exception as e:
                print(f"TTS error: {e}")

    threading.Thread(target=worker, daemon=True).start()
