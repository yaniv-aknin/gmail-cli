import base64
import email.utils
from datetime import UTC
from typing import Any

from bs4 import BeautifulSoup

from gmail_cli.cleaner import clean_email_body
from gmail_cli.documents import (
    extract_attachment_text,
    extract_text_from_docx,
    extract_text_from_pdf,
)
from gmail_cli.formatting import format_byte_size, format_contact_name


def extract_headers(payload: dict[str, Any]) -> dict[str, str]:
    headers = payload.get("headers", [])
    return {
        header.get("name", "").lower(): header.get("value", "") for header in headers
    }


def decode_base64url(encoded_data: str) -> bytes:
    try:
        return base64.urlsafe_b64decode(encoded_data.encode("utf-8"))
    except ValueError, TypeError:
        return b""


def convert_html_to_plain_text(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")
    for unneeded_tag in soup(
        ["script", "style", "head", "title", "meta", "[document]"]
    ):
        unneeded_tag.extract()
    raw_text = soup.get_text(separator="\n")
    cleaned_lines = []
    previous_was_blank = False
    for line in (item.strip() for item in raw_text.splitlines()):
        if not line:
            if not previous_was_blank:
                cleaned_lines.append("")
                previous_was_blank = True
        else:
            cleaned_lines.append(line)
            previous_was_blank = False
    return "\n".join(cleaned_lines).strip()


def parse_mime_tree(
    part: dict[str, Any], message_id: str
) -> tuple[str, str, list[dict[str, Any]]]:
    plain_text_body = ""
    html_body = ""
    attachments: list[dict[str, Any]] = []

    mime_type = part.get("mimeType", "")
    filename = part.get("filename", "")
    body_payload = part.get("body", {})
    attachment_id = body_payload.get("attachmentId")
    attachment_size = body_payload.get("size", 0)

    if filename and (attachment_id or body_payload.get("data")):
        attachments.append(
            {
                "messageId": message_id,
                "attachmentId": attachment_id or "",
                "filename": filename,
                "mimeType": mime_type,
                "sizeBytes": attachment_size,
                "inlineData": body_payload.get("data") if not attachment_id else None,
            }
        )
    elif mime_type == "text/plain" and body_payload.get("data"):
        plain_text_body += decode_base64url(body_payload["data"]).decode(
            "utf-8", errors="replace"
        )
    elif mime_type == "text/html" and body_payload.get("data"):
        html_body += decode_base64url(body_payload["data"]).decode(
            "utf-8", errors="replace"
        )

    for child_part in part.get("parts", []):
        child_plain, child_html, child_attachments = parse_mime_tree(
            child_part, message_id
        )
        if child_plain:
            plain_text_body = (
                f"{plain_text_body}\n{child_plain}" if plain_text_body else child_plain
            )
        if child_html:
            html_body = f"{html_body}\n{child_html}" if html_body else child_html
        attachments.extend(child_attachments)

    return plain_text_body, html_body, attachments


def parse_message_payload(raw_message: dict[str, Any]) -> dict[str, Any]:
    """Parse raw Gmail API message dict into structured payload with clean body and timestamp."""
    message_id = raw_message.get("id", "")
    thread_id = raw_message.get("threadId", "")
    snippet = raw_message.get("snippet", "")
    payload = raw_message.get("payload", {})
    headers = extract_headers(payload)

    plain_text_body, html_body, attachments = parse_mime_tree(payload, message_id)

    final_body = plain_text_body.strip()
    if not final_body and html_body:
        final_body = convert_html_to_plain_text(html_body)

    clean_body = clean_email_body(final_body)

    internal_date = raw_message.get("internalDate")
    timestamp: float = 0.0
    if internal_date:
        try:
            timestamp = int(internal_date) / 1000.0
        except ValueError, TypeError:
            pass
    if not timestamp and headers.get("date"):
        try:
            dt = email.utils.parsedate_to_datetime(headers["date"])
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=UTC)
            timestamp = dt.timestamp()
        except ValueError, TypeError:
            pass

    return {
        "id": message_id,
        "threadId": thread_id,
        "subject": headers.get("subject", "(No Subject)"),
        "from": headers.get("from", "(Unknown)"),
        "to": headers.get("to", ""),
        "cc": headers.get("cc", ""),
        "bcc": headers.get("bcc", ""),
        "date": headers.get("date", ""),
        "internalDate": internal_date or "",
        "timestamp": timestamp,
        "snippet": snippet,
        "body": final_body,
        "cleanBody": clean_body,
        "bodyClean": clean_body,
        "attachments": attachments,
    }


__all__ = [
    "clean_email_body",
    "convert_html_to_plain_text",
    "decode_base64url",
    "extract_attachment_text",
    "extract_headers",
    "extract_text_from_docx",
    "extract_text_from_pdf",
    "format_byte_size",
    "format_contact_name",
    "parse_message_payload",
    "parse_mime_tree",
]
