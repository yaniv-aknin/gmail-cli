import http.server
import json
import os
import sys
import threading
import time
import urllib.parse
import webbrowser
from pathlib import Path
from typing import Any

import requests
from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

CONFIG_PATH = Path.home() / ".gmail-cli.json"


def get_oauth_credentials() -> tuple[str | None, str | None]:
    client_id = os.getenv("OAUTH_CLIENT_ID")
    client_secret = os.getenv("OAUTH_CLIENT_SECRET")

    candidate_paths = [
        Path.cwd() / ".gmail-cli.json",
        CONFIG_PATH,
    ]

    for config_path in candidate_paths:
        if (not client_id or not client_secret) and config_path.exists():
            try:
                with open(config_path, "r", encoding="utf-8") as file:
                    config = json.load(file)
                oauth_client = config.get("oauth_client", {})
                if isinstance(oauth_client, dict):
                    if not client_id:
                        client_id = oauth_client.get("id")
                    if not client_secret:
                        client_secret = oauth_client.get("secret")
            except json.JSONDecodeError, OSError:
                pass

    return client_id, client_secret


OAUTH_CLIENT_ID, OAUTH_CLIENT_SECRET = get_oauth_credentials()
OAUTH_REDIRECT_URI = "http://localhost:8085/"
GMAIL_READONLY_SCOPE = "https://www.googleapis.com/auth/gmail.readonly"
GOOGLE_TOKEN_ENDPOINT = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_ENDPOINT = "https://accounts.google.com/o/oauth2/v2/auth"


def find_token_cache_path() -> Path:
    current = Path.cwd().resolve()
    for directory in (current, *current.parents):
        candidate = directory / ".token.json"
        if candidate.is_file():
            return candidate
    return current / ".token.json"


def load_token_cache() -> dict[str, Any] | None:
    cache_path = find_token_cache_path()
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as file:
                return json.load(file)
        except json.JSONDecodeError, OSError:
            return None
    return None


def save_token_cache(token_data: dict[str, Any]) -> None:
    if "expires_in" in token_data and "expires_at" not in token_data:
        token_data["expires_at"] = time.time() + float(token_data["expires_in"])
    cache_path = find_token_cache_path()
    with open(cache_path, "w", encoding="utf-8") as file:
        json.dump(token_data, file, indent=2)


def refresh_access_token(refresh_token: str) -> str | None:
    client_id, client_secret = get_oauth_credentials()
    client_id = client_id or OAUTH_CLIENT_ID
    client_secret = client_secret or OAUTH_CLIENT_SECRET

    if not client_id or not client_secret:
        print(
            "Missing OAUTH_CLIENT_ID or OAUTH_CLIENT_SECRET (check environment or ~/.gmail-cli.json)",
            file=sys.stderr,
        )
        return None

    request_payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token",
    }
    try:
        response = requests.post(
            GOOGLE_TOKEN_ENDPOINT, data=request_payload, timeout=15
        )
        if response.status_code == 200:
            updated_payload = response.json()
            cached_token = load_token_cache() or {}
            cached_token.update(updated_payload)
            cached_token["expires_at"] = time.time() + float(
                updated_payload.get("expires_in", 3600)
            )
            if "refresh_token" not in updated_payload and refresh_token:
                cached_token["refresh_token"] = refresh_token
            save_token_cache(cached_token)
            return cached_token.get("access_token")
        else:
            print(
                f"Token refresh failed ({response.status_code}): {response.text}",
                file=sys.stderr,
            )
            return None
    except requests.RequestException as error:
        print(f"Network error during token refresh: {error}", file=sys.stderr)
        return None


class OAuthCallbackHandler(http.server.BaseHTTPRequestHandler):
    acquired_code: str | None = None

    def do_GET(self) -> None:
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        code_values = query_params.get("code")
        if code_values:
            OAuthCallbackHandler.acquired_code = code_values[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html")
        self.end_headers()
        response_html = (
            "<html><body><h2>Authentication successful!</h2>"
            "<p>You can close this tab and return to the terminal.</p></body></html>"
        )
        self.wfile.write(response_html.encode("utf-8"))

    def log_message(self, format_string: str, *arguments: Any) -> None:
        return


def perform_interactive_oauth(open_browser: bool = True) -> str:
    client_id, client_secret = get_oauth_credentials()
    client_id = client_id or OAUTH_CLIENT_ID
    client_secret = client_secret or OAUTH_CLIENT_SECRET

    if not client_id or not client_secret:
        print(
            "Missing OAUTH_CLIENT_ID or OAUTH_CLIENT_SECRET (check environment or ~/.gmail-cli.json)",
            file=sys.stderr,
        )
        sys.exit(1)

    authorization_parameters = {
        "client_id": client_id,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "response_type": "code",
        "scope": GMAIL_READONLY_SCOPE,
        "access_type": "offline",
        "prompt": "consent",
    }
    authorization_url = (
        f"{GOOGLE_AUTH_ENDPOINT}?{urllib.parse.urlencode(authorization_parameters)}"
    )

    print(f"\nOAuth Authorization URL:\n{authorization_url}\n", file=sys.stderr)

    if open_browser:
        webbrowser.open(authorization_url)

    OAuthCallbackHandler.acquired_code = None
    server = http.server.HTTPServer(("localhost", 8085), OAuthCallbackHandler)

    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    if not open_browser:
        print(
            "Waiting for callback on localhost:8085 or enter authorization code manually:",
            file=sys.stderr,
        )
        prompt_thread = threading.Thread(target=_prompt_for_manual_code, daemon=True)
        prompt_thread.start()

    server_thread.join(timeout=120)

    authorization_code = OAuthCallbackHandler.acquired_code
    server.server_close()

    if not authorization_code:
        print("Failed to obtain authorization code.", file=sys.stderr)
        sys.exit(1)

    token_exchange_payload = {
        "code": authorization_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": OAUTH_REDIRECT_URI,
        "grant_type": "authorization_code",
    }
    exchange_response = requests.post(
        GOOGLE_TOKEN_ENDPOINT, data=token_exchange_payload, timeout=15
    )
    if exchange_response.status_code != 200:
        print(
            f"Failed to exchange authorization code: {exchange_response.text}",
            file=sys.stderr,
        )
        sys.exit(1)

    token_data = exchange_response.json()
    save_token_cache(token_data)
    return token_data["access_token"]


def _prompt_for_manual_code() -> None:
    try:
        user_input = input().strip()
        if user_input:
            if "code=" in user_input:
                parsed_query = urllib.parse.parse_qs(
                    urllib.parse.urlparse(user_input).query
                )
                code_values = parsed_query.get("code")
                if code_values:
                    OAuthCallbackHandler.acquired_code = code_values[0]
            else:
                OAuthCallbackHandler.acquired_code = user_input
    except EOFError, KeyboardInterrupt:
        pass


def get_valid_access_token(allow_browser: bool = False) -> str:
    cached_token = load_token_cache()
    if not cached_token or not cached_token.get("access_token"):
        print(
            "No cached access token found. Please authenticate by running: gmail auth login",
            file=sys.stderr,
        )
        sys.exit(1)

    access_token = cached_token.get("access_token")
    expires_at = cached_token.get("expires_at")

    if expires_at and time.time() >= expires_at:
        print(
            "Access token has expired. Auto-refresh is disabled.\n"
            "Please re-authenticate by running: gmail auth login",
            file=sys.stderr,
        )
        sys.exit(1)

    return access_token
