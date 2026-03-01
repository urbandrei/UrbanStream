import json
import os
import queue


class AppState:
    def __init__(self, base_dir):
        self.base_dir = base_dir
        self.nicknames_file = os.path.join(base_dir, "nicknames.json")

        # Shared mutable state
        self.chatters = {}          # {username: {"color": "#hex", "user_id": "..."}}
        self.chat_bubbles = {}      # {username: {"text": str, "time": float}}
        self.speech_queue = queue.Queue()
        self.tts_speed = 1.0
        self.auto_ads_enabled = True
        self.ad_running = False
        self.voice_chat_active = False
        self.jailed = set()             # lowercase usernames currently in jail
        self.llm_enabled = True         # master toggle for LLM assistant
        self.llm_assistant = None       # LLMAssistant instance (set by bot)
        self.headless = False           # set via --headless CLI flag

        # Nicknames (persisted to disk)
        self.nicknames = {}
        if os.path.exists(self.nicknames_file):
            with open(self.nicknames_file) as f:
                self.nicknames = json.load(f)

    def save_nicknames(self):
        with open(self.nicknames_file, "w") as f:
            json.dump(self.nicknames, f)
