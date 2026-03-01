import http.server
import json
import os
import urllib.parse
import urllib.request
import webbrowser

from urbanstream.config import CLIENT_ID, CLIENT_SECRET, REDIRECT_URI


def get_user_token(base_dir):
    """Load a saved user token or run the OAuth Authorization Code flow."""
    token_file = os.path.join(base_dir, "token.json")

    if os.path.exists(token_file):
        with open(token_file) as f:
            return json.load(f)["access_token"]

    auth_url = (
        f"https://id.twitch.tv/oauth2/authorize"
        f"?client_id={CLIENT_ID}"
        f"&redirect_uri={urllib.parse.quote(REDIRECT_URI, safe='')}"
        f"&response_type=code"
        f"&scope=chat:read+chat:edit+channel:edit:commercial+moderator:read:chatters+moderator:read:followers+moderator:manage:chat_messages+moderator:manage:banned_users"
    )

    print("Opening browser for Twitch authorization...")
    print(f"If the browser doesn't open, visit this URL manually:\n{auth_url}\n")
    webbrowser.open(auth_url)

    code = None

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal code
            params = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            code = params.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h1>Authorization successful! You can close this tab.</h1>")

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("localhost", 3000), Handler)
    print("Waiting for authorization...")
    server.handle_request()

    if not code:
        raise RuntimeError("Failed to get authorization code from Twitch")

    token_resp = urllib.request.urlopen(urllib.request.Request(
        "https://id.twitch.tv/oauth2/token",
        data=urllib.parse.urlencode({
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": REDIRECT_URI,
        }).encode(),
        method="POST",
    ))
    token_data = json.loads(token_resp.read())

    with open(token_file, "w") as f:
        json.dump(token_data, f)

    print("Token saved.")
    return token_data["access_token"]
