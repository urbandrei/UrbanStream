#!/usr/bin/env bash
set -euo pipefail

# ─── UrbanStream first-time setup for Debian/Ubuntu ───
# Run as a regular user (the script will sudo when needed).

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

info()  { echo -e "${GREEN}[+]${NC} $*"; }
warn()  { echo -e "${YELLOW}[!]${NC} $*"; }
error() { echo -e "${RED}[✗]${NC} $*"; }

# ── 1. System packages ──────────────────────────────────
info "Updating package lists..."
sudo apt-get update -qq

info "Installing system dependencies..."
sudo apt-get install -y -qq \
    python3 \
    python3-pip \
    python3-venv \
    portaudio19-dev \
    libsdl2-dev \
    libsdl2-mixer-dev \
    libsdl2-image-dev \
    libsdl2-ttf-dev \
    libespeak-dev \
    ffmpeg \
    curl \
    git

# ── 2. Python virtual environment ───────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV_DIR="$SCRIPT_DIR/venv"

if [ ! -d "$VENV_DIR" ]; then
    info "Creating Python virtual environment..."
    python3 -m venv "$VENV_DIR"
else
    info "Virtual environment already exists, skipping."
fi

source "$VENV_DIR/bin/activate"

info "Upgrading pip..."
pip install --upgrade pip -q

info "Installing Python dependencies..."
pip install -r "$SCRIPT_DIR/requirements.txt" -q

# ── 3. Ollama ────────────────────────────────────────────
if command -v ollama &>/dev/null; then
    info "Ollama is already installed."
else
    info "Installing Ollama..."
    curl -fsSL https://ollama.com/install.sh | sh
fi

# Start ollama in the background if it isn't already running
if ! pgrep -x ollama &>/dev/null; then
    info "Starting Ollama service..."
    ollama serve &>/dev/null &
    sleep 3
fi

info "Pulling LLM model (llama3:8b) — this may take a while on first run..."
ollama pull llama3:8b

info "Pulling embedding model (nomic-embed-text)..."
ollama pull nomic-embed-text

# ── 4. Project directories ───────────────────────────────
mkdir -p "$SCRIPT_DIR/knowledge"

if [ ! -f "$SCRIPT_DIR/knowledge/stream_rules.txt" ]; then
    cat > "$SCRIPT_DIR/knowledge/stream_rules.txt" <<'EOF'
Stream Rules:
1. Be respectful to everyone in chat.
2. No spam or excessive caps.
3. No hate speech, slurs, or discrimination.
4. No self-promotion or links without permission.
5. No spoilers for games or shows.
6. Listen to moderators.
7. Have fun and be positive!
EOF
    info "Created default knowledge/stream_rules.txt"
fi

# ── 5. Environment file ─────────────────────────────────
if [ ! -f "$SCRIPT_DIR/.env" ]; then
    warn "No .env file found — creating a template."
    cat > "$SCRIPT_DIR/.env" <<'EOF'
CLIENT_ID=your_twitch_client_id
CLIENT_SECRET=your_twitch_client_secret
CHANNEL=your_twitch_channel

# ── LLM settings (defaults are fine for most setups) ──
# OLLAMA_BASE_URL=http://localhost:11434
# OLLAMA_MODEL=llama3:8b
# OLLAMA_EMBED_MODEL=nomic-embed-text
# BOT_NAME=UrbanBot
# LLM_COOLDOWN_SECONDS=30
# LLM_RELEVANCE_THRESHOLD=0.6
# MOD_ENABLED=true
EOF
    warn "Edit .env with your Twitch credentials before running the bot."
else
    info ".env already exists, skipping."
fi

# ── 6. Clean up stale auth (new OAuth scope) ─────────────
if [ -f "$SCRIPT_DIR/token.json" ]; then
    warn "Removing old token.json — you'll need to re-authorize (new OAuth scopes)."
    rm "$SCRIPT_DIR/token.json"
fi

# ── Done ─────────────────────────────────────────────────
echo ""
info "Setup complete!"
echo ""
echo "  Next steps:"
echo "    1. Edit .env with your Twitch CLIENT_ID, CLIENT_SECRET, and CHANNEL"
echo "    2. Activate the venv:   source venv/bin/activate"
echo "    3. Run the bot:         python3 twitch_tts.py"
echo ""
echo "  Ollama is running in the background with llama3:8b + nomic-embed-text."
echo "  Voice commands: 'assistant on/off', 'chat on/off', 'ads on/off'"
echo ""
