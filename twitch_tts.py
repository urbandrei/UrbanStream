import argparse
import os

from urbanstream.state import AppState
from urbanstream.auth import get_user_token
from urbanstream.twitch_api import get_broadcaster_id
from urbanstream.tts import start_tts_worker
from urbanstream.bot import Bot


def main():
    parser = argparse.ArgumentParser(description="UrbanStream Twitch Bot")
    parser.add_argument(
        "--llmless", action="store_true",
        help="Run without LLM features (no moderation, no AI assistant)",
    )
    args = parser.parse_args()

    base_dir = os.path.dirname(os.path.abspath(__file__))
    state = AppState(base_dir)
    state.llm_enabled = not args.llmless

    token = get_user_token(base_dir)
    broadcaster_id = get_broadcaster_id(token)
    print(f"Broadcaster ID: {broadcaster_id}")
    start_tts_worker(state)

    if args.llmless:
        print("[Mode] LLM disabled — TTS, voice commands, and overlay only")

    bot = Bot(token, broadcaster_id, state)
    bot.run()


if __name__ == "__main__":
    main()
