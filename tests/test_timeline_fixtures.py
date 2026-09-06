from gmail_cli.timeline import build_timeline


def test_timeline_chronological_sorting_across_threads(mock_gmail_client):
    messages, errors = build_timeline(mock_gmail_client, "ce2fbe86", limit=50)
    assert not errors
    assert len(messages) == 3

    # Verify chronological sequence:
    # 1. Thread 2, Msg 1: 20:28:55
    # 2. Thread 2, Msg 2: 20:35:12
    # 3. Thread 1, Msg 1: 20:38:00
    assert messages[0]["id"] == "1a0783250b4df5dd"
    assert messages[0]["subject"] == "Test email ce2fbe86"
    assert messages[0]["from"] == "Alice <alice@example.com>"
    assert messages[0]["to"] == "Bob <bob@example.com>"

    assert messages[1]["id"] == "1a07837b83b36bc6"
    assert messages[1]["subject"] == "Re: Test email ce2fbe86"
    assert messages[1]["from"] == "Bob <bob@example.com>"
    assert messages[1]["to"] == "Alice <alice@example.com>"

    assert messages[2]["id"] == "1a0783a4a74b53f9"
    assert messages[2]["subject"] == "Follow-up ce2fbe86"
    assert messages[2]["from"] == "Bob <bob@example.com>"
    assert messages[2]["to"] == "Alice <alice@example.com>"

    # Ensure timestamps strictly increase
    assert (
        messages[0]["timestamp"] < messages[1]["timestamp"] < messages[2]["timestamp"]
    )


def test_timeline_date_filtering_since(mock_gmail_client):
    # Filter after 19:30 UTC: Msg 1 (19:28:55 UTC) should be excluded
    messages, errors = build_timeline(
        mock_gmail_client,
        "ce2fbe86",
        since="2026-09-06 19:30:00",
    )
    assert not errors
    assert len(messages) == 2
    assert messages[0]["id"] == "1a07837b83b36bc6"
    assert messages[1]["id"] == "1a0783a4a74b53f9"


def test_timeline_date_filtering_until(mock_gmail_client):
    # Filter before 19:36 UTC: Msg 3 (19:38:00 UTC) should be excluded
    messages, errors = build_timeline(
        mock_gmail_client,
        "ce2fbe86",
        until="2026-09-06 19:36:00",
    )
    assert not errors
    assert len(messages) == 2
    assert messages[0]["id"] == "1a0783250b4df5dd"
    assert messages[1]["id"] == "1a07837b83b36bc6"


def test_timeline_limit(mock_gmail_client):
    # Limit to 2 messages
    messages, errors = build_timeline(
        mock_gmail_client,
        "ce2fbe86",
        limit=2,
    )
    assert not errors
    assert len(messages) == 2
    assert messages[0]["id"] == "1a0783250b4df5dd"
    assert messages[1]["id"] == "1a07837b83b36bc6"


def test_timeline_with_extract_attachments(mock_gmail_client):
    messages, errors = build_timeline(
        mock_gmail_client,
        "ce2fbe86",
        extract_attachments=True,
    )
    assert not errors

    # Check Msg 1 attachments (DOCX and PDF)
    msg1_atts = messages[0]["attachments"]
    docx_att = next(a for a in msg1_atts if a["filename"] == "Test document.docx")
    assert "Plain text" in docx_att["extractedText"]
    assert "Row 1, Column 1" in docx_att["extractedText"]

    pdf_att = next(a for a in msg1_atts if a["filename"] == "Test document.pdf")
    assert "Plain" in pdf_att["extractedText"]

    # Check Msg 3 attachments (TXT and CSV)
    msg3_atts = messages[2]["attachments"]
    txt_att = next(a for a in msg3_atts if a["filename"] == "testfile.txt")
    assert "This is a textfile test." in txt_att["extractedText"]
    assert "سلام دنیا!" in txt_att["extractedText"]

    csv_att = next(a for a in msg3_atts if a["filename"] == "testfile.csv")
    assert '"Smith, Alice"' in csv_att["extractedText"]
