from gmail_cli.parser import parse_message_payload


def test_parse_first_message_with_docx_pdf_attachments(message_2_1_raw):
    parsed = parse_message_payload(message_2_1_raw)
    assert parsed["id"] == "1a0783250b4df5dd"
    assert parsed["threadId"] == "1a0783250b4df5dd"
    assert parsed["subject"] == "Test email ce2fbe86"
    assert parsed["from"] == "Alice <alice@example.com>"
    assert parsed["to"] == "Bob <bob@example.com>"
    assert parsed["body"] == ""
    assert parsed["cleanBody"] == ""

    # Check attachments
    attachments = parsed["attachments"]
    assert len(attachments) == 2
    filenames = {att["filename"] for att in attachments}
    assert "Test document.docx" in filenames
    assert "Test document.pdf" in filenames

    # Check sizes
    docx_att = next(a for a in attachments if a["filename"] == "Test document.docx")
    assert docx_att["sizeBytes"] == 7690
    assert "wordprocessingml" in docx_att["mimeType"]

    pdf_att = next(a for a in attachments if a["filename"] == "Test document.pdf")
    assert pdf_att["sizeBytes"] == 35951
    assert pdf_att["mimeType"] == "application/pdf"


def test_parse_reply_message_with_real_quote_stripping(message_2_2_raw):
    parsed = parse_message_payload(message_2_2_raw)
    assert parsed["id"] == "1a07837b83b36bc6"
    assert parsed["threadId"] == "1a0783250b4df5dd"
    assert parsed["subject"] == "Re: Test email ce2fbe86"
    assert parsed["from"] == "Bob <bob@example.com>"
    assert parsed["to"] == "Alice <alice@example.com>"

    # Raw body has the authored reply AND the quoted On ... wrote block
    assert "Thank you for your email." in parsed["body"]
    assert "wrote:" in parsed["body"]

    # cleanBody and bodyClean must contain ONLY the authored text
    assert parsed["cleanBody"] == "Thank you for your email."
    assert parsed["bodyClean"] == "Thank you for your email."
    assert "wrote:" not in parsed["cleanBody"]
    assert ">" not in parsed["cleanBody"]


def test_parse_second_thread_message_with_txt_csv_attachments(message_1_1_raw):
    parsed = parse_message_payload(message_1_1_raw)
    assert parsed["id"] == "1a0783a4a74b53f9"
    assert parsed["threadId"] == "1a078384134bcbea"
    assert parsed["subject"] == "Follow-up ce2fbe86"
    assert parsed["from"] == "Bob <bob@example.com>"
    assert parsed["to"] == "Alice <alice@example.com>"
    assert parsed["body"] == "Here are .txt and .csv attachments."
    assert parsed["cleanBody"] == "Here are .txt and .csv attachments."

    attachments = parsed["attachments"]
    assert len(attachments) == 2
    filenames = {att["filename"] for att in attachments}
    assert "testfile.txt" in filenames
    assert "testfile.csv" in filenames

    txt_att = next(a for a in attachments if a["filename"] == "testfile.txt")
    assert txt_att["sizeBytes"] == 334
    assert txt_att["mimeType"] == "text/plain"

    csv_att = next(a for a in attachments if a["filename"] == "testfile.csv")
    assert csv_att["sizeBytes"] == 132
    assert csv_att["mimeType"] == "text/csv"
