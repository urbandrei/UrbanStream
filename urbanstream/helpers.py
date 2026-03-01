import difflib
import re


def find_closest_user(name, chatters, nicknames):
    """Fuzzy-match a target name against chatters and nicknames.
    Returns the matched lowercase username or None."""
    name = name.lower().lstrip("@")

    # Exact match on chatter keys
    if name in chatters:
        return name

    # Exact match on reverse nickname map
    reverse_nicks = {nick.lower(): user for user, nick in nicknames.items()}
    if name in reverse_nicks:
        return reverse_nicks[name]

    # Fuzzy fallback
    candidates = list(chatters.keys()) + list(reverse_nicks.keys())
    matches = difflib.get_close_matches(name, candidates, n=1, cutoff=0.6)
    if matches:
        match = matches[0]
        return reverse_nicks.get(match, match)

    return None


def username_color(name):
    """Deterministic hex color for users with no Twitch color set."""
    h = hash(name) & 0xFFFFFF
    r = 80 + (h >> 16 & 0xFF) % 176
    g = 80 + (h >> 8 & 0xFF) % 176
    b = 80 + (h & 0xFF) % 176
    return f"#{r:02x}{g:02x}{b:02x}"


def parse_ad_duration(text):
    """Parse an ad duration from a voice command. Returns seconds or None."""
    lower = text.lower()
    word_nums = {
        "one": 1, "two": 2, "three": 3,
        "thirty": 30, "sixty": 60, "ninety": 90,
    }

    match = re.search(r'(\d+)\s*(second|minute)', lower)
    if match:
        num = int(match.group(1))
        if "minute" in match.group(2):
            return num * 60
        return num

    for word, num in word_nums.items():
        if word in lower:
            if "minute" in lower:
                return num * 60
            if "second" in lower:
                return num

    return None


def strip_twitch_emotes(message):
    """Remove Twitch emotes using the emote position data in IRC tags."""
    emotes_tag = message.tags.get("emotes")
    if not emotes_tag:
        return message.content

    text = message.content
    positions = []
    for emote in emotes_tag.split("/"):
        parts = emote.split(":")
        if len(parts) < 2:
            continue
        for pos in parts[1].split(","):
            start, end = pos.split("-")
            positions.append((int(start), int(end) + 1))

    for start, end in sorted(positions, reverse=True):
        text = text[:start] + text[end:]

    return text
