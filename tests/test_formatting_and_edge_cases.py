import pytest
from rich.console import Console

from gmail_cli.cleaner import clean_email_body
from gmail_cli.documents import extract_text_from_docx, extract_text_from_pdf
from gmail_cli.formatting import (
    format_byte_size,
    format_contact_name,
    format_duration,
    render_message_panel,
    render_search_table,
    render_thread_panel,
    render_timeline_message,
)
from gmail_cli.parser import convert_html_to_plain_text, decode_base64url
from gmail_cli.timeline import parse_date_filter


def test_formatting_durations():
    verbose, short = format_duration(3665)
    assert "1 hour" in verbose
    assert "1 minute" in verbose
    assert "5 seconds" in verbose
    assert "1h 1m 5s" == short

    verbose_zero, short_zero = format_duration(0)
    assert "0 seconds" in verbose_zero
    assert "0s" in short_zero


def test_formatting_byte_size():
    assert format_byte_size(500) == "500 B"
    assert format_byte_size(1024) == "1.0 KB"
    assert format_byte_size(1024 * 1024 * 2) == "2.0 MB"


def test_formatting_contact_names():
    assert format_contact_name("Alice <alice@example.com>") == "Alice"
    assert format_contact_name("bob@example.com") == "bob@example.com"
    assert format_contact_name("") == "(Unknown)"


def test_renderers_output(message_2_2_raw):
    from gmail_cli.parser import parse_message_payload

    console = Console(record=True, width=100)
    msg = parse_message_payload(message_2_2_raw)

    # Render message panel
    render_message_panel(console, msg, index=1, total=1, clean=True)
    panel_out = console.export_text()
    assert "Thank you for your email." in panel_out

    # Render thread panel
    thread_summary = {
        "threadId": "thread_123",
        "subject": "Test Subject",
        "messages": [msg],
    }
    render_thread_panel(console, thread_summary, clean=True)
    thread_out = console.export_text()
    assert "Thread: Test Subject" in thread_out

    # Render search table
    render_search_table(
        console,
        "test query",
        [
            {
                "threadId": "t1",
                "subject": "Sub",
                "messageCount": 1,
                "senders": ["Alice"],
                "lastDate": "today",
                "attachmentCount": 0,
            }
        ],
    )
    table_out = console.export_text()
    assert "Search Results for: 'test query'" in table_out

    # Render timeline message
    render_timeline_message(console, msg, clean=True)
    tl_out = console.export_text()
    assert "Bob -> Alice" in tl_out


def test_timeline_date_parsing_variations():
    assert parse_date_filter("2026-09-06") > 0
    assert parse_date_filter("2026-09-06 19:30") > 0
    assert parse_date_filter("2026/09/06 19:30:00") > 0
    assert parse_date_filter("06-09-2026") > 0

    with pytest.raises(ValueError, match="Unable to parse date filter"):
        parse_date_filter("not-a-date")


def test_documents_error_handling():
    # Corrupt/empty docx bytes
    assert "Error extracting DOCX text" in extract_text_from_docx(b"not a zip")
    # Corrupt/empty pdf bytes
    assert "Error extracting PDF text" in extract_text_from_pdf(b"not a pdf")


def test_parser_utilities():
    assert decode_base64url("") == b""
    html = "<p>Hello <b>World</b></p><script>bad()</script>"
    assert convert_html_to_plain_text(html) == "Hello\nWorld"


def test_cleaner_multiline_on_wrote():
    text = (
        "Done!\n\n"
        "On Sunday, September 6, 2026,\n"
        "Alice <alice@example.com> wrote:\n"
        "> Please check.\n"
    )
    assert clean_email_body(text) == "Done!"
