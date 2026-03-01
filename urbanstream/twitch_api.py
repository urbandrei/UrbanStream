import json
import urllib.error
import urllib.request

from urbanstream.config import CLIENT_ID
from urbanstream.helpers import username_color


def get_broadcaster_id(token):
    """Get the numeric user ID for the authenticated user."""
    req = urllib.request.Request(
        "https://api.twitch.tv/helix/users",
        headers={
            "Client-Id": CLIENT_ID,
            "Authorization": f"Bearer {token}",
        },
    )
    resp = urllib.request.urlopen(req)
    data = json.loads(resp.read())
    return data["data"][0]["id"]


def start_commercial(token, broadcaster_id, duration):
    """Call Twitch API to run a commercial. Returns True on success."""
    try:
        req = urllib.request.Request(
            "https://api.twitch.tv/helix/channels/commercial",
            data=json.dumps({
                "broadcaster_id": broadcaster_id,
                "length": duration,
            }).encode(),
            headers={
                "Client-Id": CLIENT_ID,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req)
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Ad API error ({e.code}): {body}")
        return False


def delete_message(token, broadcaster_id, message_id):
    """Delete a single chat message via Twitch API. Returns True on success."""
    try:
        url = (
            f"https://api.twitch.tv/helix/moderation/chat"
            f"?broadcaster_id={broadcaster_id}"
            f"&moderator_id={broadcaster_id}"
            f"&message_id={message_id}"
        )
        req = urllib.request.Request(
            url,
            headers={
                "Client-Id": CLIENT_ID,
                "Authorization": f"Bearer {token}",
            },
            method="DELETE",
        )
        urllib.request.urlopen(req)
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Delete message API error ({e.code}): {body}")
        return False


def timeout_user(token, broadcaster_id, user_id, duration, reason=""):
    """Timeout a user via Twitch API. Returns True on success."""
    try:
        req = urllib.request.Request(
            f"https://api.twitch.tv/helix/moderation/bans"
            f"?broadcaster_id={broadcaster_id}&moderator_id={broadcaster_id}",
            data=json.dumps({
                "data": {
                    "user_id": user_id,
                    "duration": duration,
                    "reason": reason,
                },
            }).encode(),
            headers={
                "Client-Id": CLIENT_ID,
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json",
            },
            method="POST",
        )
        urllib.request.urlopen(req)
        return True
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        print(f"Timeout API error ({e.code}): {body}")
        return False


def fetch_chatters_who_follow(token, broadcaster_id):
    """Fetch current chatters, then filter to only those who are followers."""
    req = urllib.request.Request(
        f"https://api.twitch.tv/helix/chat/chatters"
        f"?broadcaster_id={broadcaster_id}&moderator_id={broadcaster_id}&first=1000",
        headers={
            "Client-Id": CLIENT_ID,
            "Authorization": f"Bearer {token}",
        },
    )
    try:
        resp = urllib.request.urlopen(req)
        data = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        print(f"Chatters API error ({e.code}): {e.read().decode()}")
        return {}

    users = data.get("data", [])
    print(f"[Overlay] Found {len(users)} chatters")
    if not users:
        return {}

    followers = set()
    for u in users:
        check_req = urllib.request.Request(
            f"https://api.twitch.tv/helix/channels/followers"
            f"?broadcaster_id={broadcaster_id}&user_id={u['user_id']}",
            headers={
                "Client-Id": CLIENT_ID,
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            check_resp = urllib.request.urlopen(check_req)
            check_data = json.loads(check_resp.read())
            if check_data.get("data"):
                followers.add(u["user_id"])
        except urllib.error.HTTPError as e:
            print(f"[Overlay] Follower check failed for {u['user_login']}: {e.code}")

    print(f"[Overlay] {len(followers)} of {len(users)} chatters are followers")
    users = [u for u in users if u["user_id"] in followers]
    if not users:
        return {}

    result = {}
    for i in range(0, len(users), 100):
        batch = users[i:i + 100]
        params = "&".join(f"user_id={u['user_id']}" for u in batch)
        color_req = urllib.request.Request(
            f"https://api.twitch.tv/helix/chat/color?{params}",
            headers={
                "Client-Id": CLIENT_ID,
                "Authorization": f"Bearer {token}",
            },
        )
        try:
            color_resp = urllib.request.urlopen(color_req)
            color_data = json.loads(color_resp.read())
            color_map = {c["user_id"]: c["color"] for c in color_data.get("data", [])}
        except urllib.error.HTTPError:
            color_map = {}

        for u in batch:
            uid = u["user_id"]
            name = u["user_login"]
            color = color_map.get(uid, "")
            if not color:
                color = username_color(name)
            result[name] = {"color": color, "user_id": uid}

    return result
