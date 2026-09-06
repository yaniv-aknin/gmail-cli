import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def fixtures_dir() -> Path:
    return FIXTURES_DIR


@pytest.fixture
def search_threads_raw() -> dict:
    with open(FIXTURES_DIR / "search_threads_raw.json") as f:
        return json.load(f)


@pytest.fixture
def thread_1_raw() -> dict:
    with open(FIXTURES_DIR / "thread_1_1a078384134bcbea.json") as f:
        return json.load(f)


@pytest.fixture
def thread_2_raw() -> dict:
    with open(FIXTURES_DIR / "thread_2_1a0783250b4df5dd.json") as f:
        return json.load(f)


@pytest.fixture
def message_1_1_raw() -> dict:
    with open(FIXTURES_DIR / "message_1_1_1a0783a4a74b53f9.json") as f:
        return json.load(f)


@pytest.fixture
def message_2_1_raw() -> dict:
    with open(FIXTURES_DIR / "message_2_1_1a0783250b4df5dd.json") as f:
        return json.load(f)


@pytest.fixture
def message_2_2_raw() -> dict:
    with open(FIXTURES_DIR / "message_2_2_1a07837b83b36bc6.json") as f:
        return json.load(f)


@pytest.fixture
def docx_bytes() -> bytes:
    with open(FIXTURES_DIR / "Test document.docx", "rb") as f:
        return f.read()


@pytest.fixture
def pdf_bytes() -> bytes:
    with open(FIXTURES_DIR / "Test document.pdf", "rb") as f:
        return f.read()


@pytest.fixture
def txt_bytes() -> bytes:
    with open(FIXTURES_DIR / "testfile.txt", "rb") as f:
        return f.read()


@pytest.fixture
def csv_bytes() -> bytes:
    with open(FIXTURES_DIR / "testfile.csv", "rb") as f:
        return f.read()


@pytest.fixture
def mock_gmail_client(
    search_threads_raw,
    thread_1_raw,
    thread_2_raw,
    message_1_1_raw,
    message_2_1_raw,
    message_2_2_raw,
    docx_bytes,
    pdf_bytes,
    txt_bytes,
    csv_bytes,
) -> MagicMock:
    client = MagicMock()
    client.search_threads.return_value = search_threads_raw

    threads_map = {
        "1a078384134bcbea": thread_1_raw,
        "1a0783250b4df5dd": thread_2_raw,
    }
    messages_map = {
        "1a0783a4a74b53f9": message_1_1_raw,
        "1a0783250b4df5dd": message_2_1_raw,
        "1a07837b83b36bc6": message_2_2_raw,
    }

    client.get_thread.side_effect = lambda tid, format_type="full": threads_map[tid]
    client.get_message.side_effect = lambda mid, format_type="full": messages_map[mid]

    def fake_get_attachment(msg_id, att_id):
        all_sources = list(messages_map.values())
        for t in threads_map.values():
            all_sources.extend(t.get("messages", []))
        for msg in all_sources:
            if msg.get("id") == msg_id:
                for part in msg.get("payload", {}).get("parts", []):
                    part_att_id = part.get("body", {}).get("attachmentId")
                    fn = part.get("filename", "")
                    if part_att_id == att_id or fn == att_id:
                        if fn.endswith(".docx"):
                            return docx_bytes
                        if fn.endswith(".pdf"):
                            return pdf_bytes
                        if fn.endswith(".txt"):
                            return txt_bytes
                        if fn.endswith(".csv"):
                            return csv_bytes
        raise KeyError(f"Attachment {att_id} not found in message {msg_id}")

    client.get_attachment.side_effect = fake_get_attachment
    return client
