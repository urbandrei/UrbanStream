import os

from urbanstream.state import AppState
from urbanstream.auth import get_user_token
from urbanstream.twitch_api import get_broadcaster_id
from urbanstream.tts import start_tts_worker
from urbanstream.bot import Bot


def main():
    base_dir = os.path.dirname(os.path.abspath(__file__))
    state = AppState(base_dir)
    token = get_user_token(base_dir)
    broadcaster_id = get_broadcaster_id(token)
    print(f"Broadcaster ID: {broadcaster_id}")
    start_tts_worker(state)
    bot = Bot(token, broadcaster_id, state)
    bot.run()


if __name__ == "__main__":
    main()
