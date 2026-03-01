import os
from dotenv import load_dotenv

load_dotenv()

CLIENT_ID = os.environ["CLIENT_ID"]
CLIENT_SECRET = os.environ["CLIENT_SECRET"]
CHANNEL = os.environ["CHANNEL"]
REDIRECT_URI = "http://localhost:3000"
