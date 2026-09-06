from gmail_cli.cleaner import clean_email_body


def test_cleaner_standard_reply_quoted_text():
    raw = (
        "Hi Bob,\n\n"
        "Here is the scope note.\n\n"
        "On Sun, Sep 6, 2026, Alice <alice@example.com> wrote:\n"
        "> Can you send the scope note?\n"
        "> Thanks,\n"
        "> Alice\n"
    )
    cleaned = clean_email_body(raw)
    assert "Hi Bob," in cleaned
    assert "Here is the scope note." in cleaned
    assert "Can you send the scope note?" not in cleaned
    assert "Alice <alice@example.com> wrote:" not in cleaned


def test_cleaner_outlook_original_message_boundary():
    raw = (
        "Approved.\n\n"
        "-----Original Message-----\n"
        "From: Alice <alice@example.com>\n"
        "Sent: Sunday, September 6, 2026 8:00 PM\n"
        "To: Bob <bob@example.com>\n"
        "Subject: Scope Note\n\n"
        "Please review.\n"
    )
    cleaned = clean_email_body(raw)
    assert cleaned == "Approved."


def test_cleaner_inline_replies():
    raw = (
        "On Sun, Sep 6, 2026, Alice <alice@example.com> wrote:\n"
        "> Can you verify the director list?\n"
        "Yes, verified.\n\n"
        "> When is the call?\n"
        "Tomorrow at 10am.\n"
    )
    cleaned = clean_email_body(raw)
    assert "Yes, verified." in cleaned
    assert "Tomorrow at 10am." in cleaned
    assert "Can you verify" not in cleaned
