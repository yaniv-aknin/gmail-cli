from gmail_cli.documents import (
    extract_attachment_text,
    extract_text_from_docx,
    extract_text_from_pdf,
)


def test_real_docx_fixture_extraction(docx_bytes):
    text = extract_text_from_docx(docx_bytes)
    assert "Plain text" in text
    assert "Bold text" in text
    assert "Red text" in text
    assert "Heading 1" in text
    assert "Bullet" in text
    assert "One" in text and "Two" in text and "Three" in text
    # Verify table row extraction with pipe delimiter
    assert "Row 1, Column 1 | Row 1, Column 2 | Row 1, Column 3" in text
    assert "Row 2, Column 1 | Row 2, Column 2 | Row 2, Column 3" in text


def test_real_pdf_fixture_extraction(pdf_bytes):
    text = extract_text_from_pdf(pdf_bytes)
    # PDF extracts word tokens and structure
    assert "Plain" in text and "text" in text
    assert "Bold" in text
    assert "Heading" in text
    assert "Row" in text and "Column" in text


def test_real_txt_fixture_extraction_utf8_multilingual(txt_bytes):
    text = extract_attachment_text("testfile.txt", "text/plain", txt_bytes)
    assert text is not None
    assert "This is a textfile test." in text
    # Verify French accented characters
    assert "é, è, ê, ë, à, â, ç, î, ï, ô, ù, û, ü, œ" in text
    # Verify right-to-left Farsi script
    assert "سلام دنیا!" in text
    assert "گ، چ، پ، ژ" in text


def test_real_csv_fixture_extraction_structured(csv_bytes):
    text = extract_attachment_text("testfile.csv", "text/csv", csv_bytes)
    assert text is not None
    assert "id,name,description,notes" in text
    # Verify quoted field containing a comma
    assert '"Smith, Alice"' in text
    # Verify quoted text containing double quotes
    assert 'Contains ""quoted"" text' in text
    # Verify multiline record
    assert "Line 1\nLine 2" in text


def test_extract_attachment_text_unsupported():
    png_bytes = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR"
    assert extract_attachment_text("image.png", "image/png", png_bytes) is None
