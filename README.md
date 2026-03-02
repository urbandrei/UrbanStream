# UrbanStream

A Twitch bot with text-to-speech, voice commands, AI-powered moderation, an interactive overlay, and a locally-hosted LLM assistant via Ollama.

## Requirements

- Python 3.10+
- [Ollama](https://ollama.com/) running locally
- A [Twitch application](https://dev.twitch.tv/console/apps) with a Client ID and Secret
- Microphone and speakers (optional, not needed in headless mode)

## Setup

```bash
# Create a virtual environment and install dependencies
python -m venv venv
source venv/bin/activate        # Linux/Mac
.\venv\Scripts\Activate.ps1     # Windows PowerShell
pip install -r requirements.txt

# Pull the Ollama models
ollama pull llama3.2:3b
ollama pull llama3:8b
ollama pull nomic-embed-text

# Create a .env file with your credentials (see Configuration below)
cp .env.example .env

# Create the knowledge directory
mkdir knowledge
```

## Usage

```bash
# Standard mode (TTS + voice recognition + overlay)
python twitch_tts.py

# Headless mode (no mic/speakers/browser — for servers)
python twitch_tts.py --headless
```

In headless mode, the OAuth flow prints a URL for you to open in a browser elsewhere. Paste the redirect URL back into the terminal.

## Configuration

All settings are loaded from a `.env` file in the project root.

### Required

| Variable | Description |
|----------|-------------|
| `CLIENT_ID` | Twitch application Client ID |
| `CLIENT_SECRET` | Twitch application Client Secret |
| `CHANNEL` | Your Twitch channel name |

### Bot Identity

| Variable | Default | Description |
|----------|---------|-------------|
| `BOT_NAME` | `UrbanBot` | Name the bot uses in chat |

### Ollama / LLM

| Variable | Default | Description |
|----------|---------|-------------|
| `OLLAMA_BASE_URL` | `http://localhost:11434` | Ollama server URL |
| `OLLAMA_FAST_MODEL` | `llama3.2:3b` | Model for quick responses and moderation screening |
| `OLLAMA_BIG_MODEL` | `llama3:8b` | Model for complex queries and moderation review |
| `OLLAMA_EMBED_MODEL` | `nomic-embed-text` | Embedding model for RAG |
| `OLLAMA_KEEP_ALIVE` | `-1` | How long to keep models loaded (`-1` = forever) |
| `OLLAMA_NUM_CTX` | `1024` | Context window size in tokens |

### Response Behavior

| Variable | Default | Description |
|----------|---------|-------------|
| `LLM_COOLDOWN_SECONDS` | `30` | Minimum seconds between bot responses |
| `LLM_RELEVANCE_THRESHOLD` | `0.6` | Relevance score needed to trigger a response |
| `LLM_MAX_RESPONSE_TOKENS` | `150` | Max tokens per response |
| `LLM_CONTEXT_WINDOW` | `20` | Number of recent messages included as context |

### RAG / Knowledge Base

| Variable | Default | Description |
|----------|---------|-------------|
| `CHROMA_PERSIST_DIR` | `chroma_data` | Directory for ChromaDB vector storage |
| `RAG_TOP_K` | `5` | Number of knowledge documents retrieved per query |

Place `.txt` or `.md` files in the `knowledge/` directory. They are loaded into the vector database on startup and used as context for LLM responses.

### Moderation

| Variable | Default | Description |
|----------|---------|-------------|
| `MOD_ENABLED` | `true` | Enable/disable AI moderation |
| `MOD_WARN_THRESHOLD` | `0.6` | Severity score to warn a user |
| `MOD_JAIL_THRESHOLD` | `0.75` | Severity score to jail a user |
| `MOD_TIMEOUT_THRESHOLD` | `0.85` | Severity score to timeout a user |
| `MOD_TIMEOUT_DURATION` | `300` | Timeout duration in seconds |

## Features

### Text-to-Speech

All chat messages are read aloud using Google TTS. The streamer can control TTS speed with `!tts-speed <value>` (range 0.1 to 10.0). Disabled in headless mode.

### Voice Commands

The bot continuously listens to the streamer's microphone and recognizes the following spoken commands:

| Command | Action |
|---------|--------|
| `chat on` / `chat off` | Toggle voice-to-chat transcription |
| `ads on` / `ads off` | Toggle automatic ad loop (every 20 min) |
| `run N seconds/minutes of ads` | Run a commercial of the specified length |
| `assistant on` / `assistant off` | Toggle LLM assistant |
| `jail <username>` | Jail a user |
| `free <username>` | Unjail a user |

Voice transcriptions are always forwarded to the LLM assistant (even when voice-to-chat is off), so the streamer can ask questions or give commands by speaking naturally.

### Chat Commands

| Command | Who | Action |
|---------|-----|--------|
| `!nickname @user name` | Streamer | Set a display name for a user (used in TTS and overlay) |
| `!tts-speed <value>` | Streamer | Set TTS playback speed |
| `!jail <user>` | Streamer / Mods | Jail a user — text messages are deleted, emote-only messages still show |
| `!free <user>` | Streamer / Mods | Release a jailed user |

User matching is fuzzy — partial or misspelled names are matched against current chatters and nicknames.

### LLM Assistant

The bot runs a locally-hosted LLM via Ollama with a two-tier model setup:

- **Fast model** (3b) handles routine responses and moderation screening. It stays preloaded in memory for low latency.
- **Big model** (8b) is called when the fast model produces a weak response (empty or under 10 characters). When escalating, the bot sends "Let me think about that a little more" to chat and TTS before generating the full response.

The LLM currently only responds to **streamer voice transcriptions**, not general chat. Chat messages are still recorded as context and run through moderation.

The streamer can ask about moderation decisions by voice (e.g., "why did you jail X?") and the bot will look up the moderation history and respond.

#### Personality

Bot personality is defined in `PERSONALITY.md` at the project root. Edit this file to change how the bot communicates. If the file is missing, a default concise/professional personality is used.

#### Knowledge Base

Place `.txt` or `.md` files in the `knowledge/` directory to give the bot information about your stream, rules, schedule, etc. These are embedded into a vector database and retrieved when relevant to a query.

### AI Moderation

Every chat message (except the streamer's) is evaluated for rule violations using a two-step process:

1. **Fast screen** — the 3b model checks for spam, hate speech, self-promotion, spoilers, and toxicity
2. **Big review** — if flagged, the 8b model reviews it to filter out false positives (sarcasm, humor, etc.)

Actions escalate based on severity and prior warnings:

| Severity | Prior Warnings | Action |
|----------|---------------|--------|
| >= 0.60 | 0 | Warn |
| >= 0.60 | 2+ | Jail |
| >= 0.60 | 3+ | Timeout |
| >= 0.75 | Any | Jail |
| >= 0.85 | Any | Timeout |

All moderation decisions are logged to `moderation.db` (SQLite) for audit. Prior user history is included in the screening prompt so the model considers repeat offenders.

### Overlay

An interactive browser source overlay runs at `http://localhost:8080/overlay.html`. Add it as a Browser Source in OBS.

- **Animated characters** — each chatter gets a walking pixel-art sprite with their Twitch color
- **Chat bubbles** — recent messages appear above each character for 10 seconds
- **Jail cage** — jailed users are visually placed in a cage with bars; freed users fall out with an animation
- **Auto-sync** — polls the bot every second for current chatters, messages, and jail status

### Automatic Ads

When enabled (`ads on` voice command), the bot runs a 60-second commercial every 20 minutes. Voice-to-chat transcription pauses during ads and a TTS notification plays at start and end.

## File Structure

```
UrbanStream/
  twitch_tts.py          # Entry point
  PERSONALITY.md         # Bot personality definition
  requirements.txt       # Python dependencies
  bot.png               # Sprite sheet for overlay characters
  knowledge/            # Knowledge base documents (.txt, .md)
  overlay/              # Overlay HTML/CSS/JS
  urbanstream/
    auth.py             # OAuth flow (browser + headless)
    bot.py              # Twitch IRC client, chat commands
    config.py           # Core env config
    helpers.py          # Fuzzy matching, color gen, emote stripping
    llm_assistant.py    # LLM orchestrator
    llm_config.py       # LLM env config
    mod_db.py           # SQLite moderation audit log
    moderation.py       # Two-step AI moderation engine
    ollama_client.py    # Async Ollama HTTP client
    overlay_server.py   # HTTP server for overlay
    rag.py              # ChromaDB RAG pipeline
    smart_filter.py     # Response relevance scoring
    state.py            # Shared application state
    tts.py              # Google TTS worker
    twitch_api.py       # Twitch Helix API calls
    voice.py            # Voice recognition listener
```

## Persisted Data

| File/Directory | Contents | Gitignored |
|---------------|----------|------------|
| `token.json` | OAuth access token | Yes |
| `nicknames.json` | User display name aliases | Yes |
| `moderation.db` | Moderation action audit log | Yes |
| `chroma_data/` | ChromaDB vector embeddings | Yes |
| `knowledge/` | Knowledge base documents | Yes |
| `.env` | Secrets and configuration | Yes |
