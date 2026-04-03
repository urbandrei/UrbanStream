import random
import string
import time

from urbanstream.config import PLATE_REWARD


class JailMinigame:
    def __init__(self):
        self._challenges = {}  # {user_id: {"plate": str, "completed": int}}

    @staticmethod
    def generate_plate():
        letters = "".join(random.choices(string.ascii_uppercase, k=3))
        digits = "".join(random.choices(string.digits, k=4))
        return f"{letters} {digits}"

    def get_or_create_challenge(self, user_id):
        if user_id not in self._challenges:
            self._challenges[user_id] = {
                "plate": self.generate_plate(),
                "completed": 0,
            }
        return self._challenges[user_id]

    def check_answer(self, user_id, answer):
        challenge = self._challenges.get(user_id)
        if not challenge:
            return False, 0
        if answer.strip().upper() == challenge["plate"]:
            challenge["completed"] += 1
            challenge["plate"] = self.generate_plate()
            return True, challenge["completed"]
        return False, challenge["completed"]

    def clear_user(self, user_id):
        self._challenges.pop(user_id, None)
