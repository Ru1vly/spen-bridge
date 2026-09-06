"""
Local network helpers for the GUI: LAN IP detection and a tiny background
HTTP server used to serve the APK for QR-code pairing.
"""

import http.server
import logging
from pathlib import Path
import socket
import socketserver
import subprocess
import threading
from typing import Optional

logger = logging.getLogger("SPenGUI")

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def get_local_ip() -> str:
    """Detect local LAN IP address."""
    try:
        res = subprocess.run(
            ["ip", "-4", "route", "get", "1.1.1.1"],
            capture_output=True,
            text=True,
            timeout=1.0,
            check=False,
        )
        parts = res.stdout.split()
        if "src" in parts:
            idx = parts.index("src")
            if idx + 1 < len(parts):
                return parts[idx + 1]
    except Exception:
        pass
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(("8.8.8.8", 80))
        ip = s.getsockname()[0]
        s.close()
        return ip
    except Exception:
        return "127.0.0.1"


class MiniHttpServer:
    def __init__(self, port=8080, directory=str(REPO_ROOT)):
        self.port = port
        self.directory = directory
        self.httpd: Optional[socketserver.TCPServer] = None
        self._thread: Optional[threading.Thread] = None

    def start(self):
        if self.httpd is not None:
            return

        directory = self.directory

        class Handler(http.server.SimpleHTTPRequestHandler):
            def __init__(self, *args, **kwargs):
                super().__init__(*args, directory=directory, **kwargs)

            def log_message(self, format, *args):
                pass  # suppress console spam

        socketserver.TCPServer.allow_reuse_address = True
        try:
            self.httpd = socketserver.TCPServer(("0.0.0.0", self.port), Handler)
            self._thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
            self._thread.start()
            logger.info(f"APK download HTTP server listening on port {self.port}")
        except Exception as e:
            logger.warning(f"Could not start APK HTTP server: {e}")

    def stop(self):
        if self.httpd:
            try:
                self.httpd.server_close()
            except Exception:
                pass
            try:
                threading.Thread(target=self.httpd.shutdown, daemon=True).start()
            except Exception:
                pass
            self.httpd = None
