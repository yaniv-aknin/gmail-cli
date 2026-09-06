from typing import Any

import requests

from gmail_cli.auth import get_valid_access_token
from gmail_cli.parser import decode_base64url


class GmailClient:
    GMAIL_API_BASE_URL = "https://gmail.googleapis.com/gmail/v1/users/me"

    def __init__(self, allow_browser: bool = False):
        self.access_token = get_valid_access_token(allow_browser=allow_browser)

    def _execute_request(
        self, method: str, endpoint: str, **kwargs: Any
    ) -> requests.Response:
        request_url = f"{self.GMAIL_API_BASE_URL}/{endpoint}"
        headers = kwargs.pop("headers", {})
        headers["Authorization"] = f"Bearer {self.access_token}"

        response = requests.request(method, request_url, headers=headers, **kwargs)
        if response.status_code == 401:
            raise RuntimeError(
                "Gmail API request unauthorized (401). Token may be invalid or expired. "
                "Please run 'gmail auth login' to re-authenticate."
            )
        return response

    def search_threads(
        self,
        query: str,
        limit: int = 20,
        page_token: str | None = None,
        include_spam_trash: bool = False,
    ) -> dict[str, Any]:
        if page_token:
            query_parameters = {
                "q": query,
                "maxResults": min(limit, 100),
                "includeSpamTrash": include_spam_trash,
                "pageToken": page_token,
            }
            response = self._execute_request("GET", "threads", params=query_parameters)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Gmail thread search failed ({response.status_code}): {response.text}"
                )
            return response.json()

        all_threads: list[dict[str, Any]] = []
        current_page_token = None
        next_page_token = None

        while len(all_threads) < limit:
            page_limit = min(limit - len(all_threads), 100)
            query_parameters = {
                "q": query,
                "maxResults": page_limit,
                "includeSpamTrash": include_spam_trash,
            }
            if current_page_token:
                query_parameters["pageToken"] = current_page_token

            response = self._execute_request("GET", "threads", params=query_parameters)
            if response.status_code != 200:
                raise RuntimeError(
                    f"Gmail thread search failed ({response.status_code}): {response.text}"
                )
            data = response.json()
            threads = data.get("threads", [])
            all_threads.extend(threads)
            next_page_token = data.get("nextPageToken")
            if not next_page_token or not threads:
                break
            current_page_token = next_page_token

        return {
            "threads": all_threads[:limit],
            "nextPageToken": next_page_token,
            "resultSizeEstimate": len(all_threads),
        }

    def get_thread(self, thread_id: str, format_type: str = "full") -> dict[str, Any]:
        response = self._execute_request(
            "GET", f"threads/{thread_id}", params={"format": format_type}
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch thread {thread_id} ({response.status_code}): {response.text}"
            )
        return response.json()

    def get_message(self, message_id: str, format_type: str = "full") -> dict[str, Any]:
        response = self._execute_request(
            "GET", f"messages/{message_id}", params={"format": format_type}
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch message {message_id} ({response.status_code}): {response.text}"
            )
        return response.json()

    def get_attachment(self, message_id: str, attachment_id: str) -> bytes:
        response = self._execute_request(
            "GET", f"messages/{message_id}/attachments/{attachment_id}"
        )
        if response.status_code != 200:
            raise RuntimeError(
                f"Failed to fetch attachment {attachment_id} ({response.status_code}): {response.text}"
            )
        encoded_data = response.json().get("data", "")
        return decode_base64url(encoded_data)
