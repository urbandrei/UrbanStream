import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
CHANNEL = os.environ["CHANNEL"]
REDIRECT_URI = "http://localhost:3000"

# Channel point reward IDs (optional — leave blank to disable)
REWARD_ACCENT = os.getenv("REWARD_ACCENT", "")
REWARD_TRANSLATE = os.getenv("REWARD_TRANSLATE", "")
REWARD_BABEL = os.getenv("REWARD_BABEL", "")
REWARD_AD = os.getenv("REWARD_AD", "")
REWARD_AD_DURATION = int(os.getenv("REWARD_AD_DURATION", "60"))  # seconds
