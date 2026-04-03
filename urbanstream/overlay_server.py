import http.server
import json
import os
import threading
import time

from urbanstream.helpers import username_color


def start_overlay_server(state):
    """Start the overlay HTTP server on port 8080 in a daemon thread."""
    overlay_dir = os.path.join(state.base_dir, "overlay")

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            path = self.path

            if path == "/api/chatters":
                now = time.time()
                merged = {}
                for user, info in state.chatters.items():
                    entry = dict(info)
                    bubble = state.chat_bubbles.get(user)
                    if bubble and now - bubble["time"] < 10:
                        entry["msg"] = bubble["text"]
                    if user in state.jailed:
                        entry["jailed"] = True
                    merged[user] = entry
                # Inject jailed users who left the channel (so they stay visible)
                for user in state.jailed:
                    if user not in merged:
                        merged[user] = {
                            "color": username_color(user),
                            "user_id": "",
                            "jailed": True,
                        }
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Access-Control-Allow-Origin", "*")
                self.end_headers()
                self.wfile.write(json.dumps(merged).encode())

            elif path == "/bot.png":
                png_path = os.path.join(state.base_dir, "bot.png")
                with open(png_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "image/png")
                self.send_header("Cache-Control", "public, max-age=3600")
                self.end_headers()
                self.wfile.write(data)
            elif path == "/overlay.css":
                css_path = os.path.join(overlay_dir, "overlay.css")
                with open(css_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/css")
                self.end_headers()
                self.wfile.write(data)
            elif path == "/overlay.js":
                js_path = os.path.join(overlay_dir, "overlay.js")
                with open(js_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "application/javascript")
                self.end_headers()
                self.wfile.write(data)
            elif path == "/" or path == "":
                html_path = os.path.join(overlay_dir, "overlay.html")
                with open(html_path, "rb") as f:
                    data = f.read()
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(data)
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):
            pass

    server = http.server.HTTPServer(("localhost", 8080), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    print("Overlay server running at http://localhost:8080")
