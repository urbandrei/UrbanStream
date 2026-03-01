import os
import tempfile
import threading
import time

from gtts import gTTS
import pygame


def start_tts_worker(state):
    """Start the TTS background thread consuming from state.speech_queue."""
    def worker():
        pygame.mixer.init()
        while True:
            text = state.speech_queue.get()
            try:
                tts = gTTS(text=text, lang="en")
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
