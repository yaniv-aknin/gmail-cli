import email.utils
from datetime import UTC, datetime
from typing import TYPE_CHECKING, Any

import requests

from gmail_cli.documents import extract_attachment_text
from gmail_cli.parser import decode_base64url, parse_message_payload

if TYPE_CHECKING:
    from gmail_cli.client import GmailClient

DATE_FORMATS = [
    "%Y-%m-%d",
    "%Y-%m-%d %H:%M",
    "%Y-%m-%d %H:%M:%S",
    "%Y/%m/%d",
    "%Y/%m/%d %H:%M",
    "%Y/%m/%d %H:%M:%S",
    "%d-%m-%Y",
    "%d/%m/%Y",
]


def parse_date_filter(date_str: str) -> float:
    """Parse a date/datetime string into an epoch timestamp float (in UTC)."""
    cleaned = date_str.strip()
    try:
        dt = datetime.fromisoformat(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError:
        pass

    try:
        dt = email.utils.parsedate_to_datetime(cleaned)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=UTC)
        return dt.timestamp()
    except ValueError, TypeError:
        pass

    for fmt in DATE_FORMATS:
        try:
            dt = datetime.strptime(cleaned, fmt).replace(tzinfo=UTC)
            return dt.timestamp()
        except ValueError:
            pass

    raise ValueError(f"Unable to parse date filter: '{date_str}'")


def extract_attachments_for_messages(
    client: GmailClient, messages: list[dict[str, Any]]
) -> None:
    """Fetch and extract text content for all document attachments across messages."""
    for msg in messages:
        for att in msg.get("attachments", []):
            if "extractedText" not in att or att["extractedText"] is None:
                file_bytes = b""
                if att.get("attachmentId"):
                    try:
                        file_bytes = client.get_attachment(
                            msg.get("id") or att.get("messageId", ""),
                            att["attachmentId"],
                        )
                    except (
                        requests.RequestException,
                        RuntimeError,
                        KeyError,
                        OSError,
                        ValueError,
                    ) as error:
                        att["extractedText"] = f"Error fetching attachment: {error}"
                        continue
                elif att.get("inlineData"):
                    file_bytes = decode_base64url(att["inlineData"])

                if file_bytes:
                    att["extractedText"] = extract_attachment_text(
                        att["filename"], att["mimeType"], file_bytes
                    )


def build_timeline(
    client: GmailClient,
    query: str,
    limit: int = 50,
    since: str | None = None,
    until: str | None = None,
    extract_attachments: bool = False,
) -> tuple[list[dict[str, Any]], list[str]]:
    """Flatten messages across threads matching query into a chronological sequence."""
    after_ts = parse_date_filter(since) if since else None
    before_ts = parse_date_filter(until) if until else None

    raw_response = client.search_threads(
        query=query,
        limit=max(limit, 50),
        include_spam_trash=False,
    )
    thread_items = raw_response.get("threads", [])

    timeline_messages: list[dict[str, Any]] = []
    errors: list[str] = []

    for item in thread_items:
        thread_id = item["id"]
        try:
            full_thread = client.get_thread(thread_id, format_type="full")
            raw_messages = full_thread.get("messages", [])
            for raw_msg in raw_messages:
                parsed_msg = parse_message_payload(raw_msg)
                ts = parsed_msg.get("timestamp") or 0.0

                if after_ts is not None and ts < after_ts:
                    continue
                if before_ts is not None and ts > before_ts:
                    continue

                timeline_messages.append(parsed_msg)
        except (
            requests.RequestException,
            RuntimeError,
            KeyError,
            OSError,
            ValueError,
        ) as error:
            errors.append(f"Failed to fetch thread {thread_id}: {error}")

    timeline_messages.sort(key=lambda m: m.get("timestamp", 0.0))
    if len(timeline_messages) > limit:
        timeline_messages = timeline_messages[:limit]

    if extract_attachments:
        extract_attachments_for_messages(client, timeline_messages)

    return timeline_messages, errors
