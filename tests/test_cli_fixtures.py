import json
from unittest.mock import patch

from typer.testing import CliRunner

from gmail_cli.cli import app

runner = CliRunner()


def test_cli_search_summary_and_full(mock_gmail_client):
    with patch("gmail_cli.cli.GmailClient", return_value=mock_gmail_client):
        # Summary search
        res = runner.invoke(app, ["search", "ce2fbe86", "--json"])
        assert res.exit_code == 0
        data = json.loads(res.output)
        assert data["resultCount"] == 2
        assert len(data["threads"]) == 2
        # Without --full, messages key is not embedded
        assert "messages" not in data["threads"][0]

        # Full search with embedded messages
        res_full = runner.invoke(app, ["search", "ce2fbe86", "--full", "--json"])
        assert res_full.exit_code == 0
        data_full = json.loads(res_full.output)
        assert "messages" in data_full["threads"][0]
        assert "messages" in data_full["threads"][1]


def test_cli_thread_single_and_batch(mock_gmail_client):
    with patch("gmail_cli.cli.GmailClient", return_value=mock_gmail_client):
        # Single thread positional returns single object
        res_single = runner.invoke(app, ["thread", "1a078384134bcbea", "--json"])
        assert res_single.exit_code == 0
        data_single = json.loads(res_single.output)
        assert isinstance(data_single, dict)
        assert data_single["threadId"] == "1a078384134bcbea"
        assert data_single["messageCount"] == 1

        # Multiple threads positional returns list of objects
        res_multi = runner.invoke(
            app, ["thread", "1a078384134bcbea", "1a0783250b4df5dd", "--json"]
        )
        assert res_multi.exit_code == 0
        data_multi = json.loads(res_multi.output)
        assert isinstance(data_multi, list)
        assert len(data_multi) == 2
        assert data_multi[0]["threadId"] == "1a078384134bcbea"
        assert data_multi[1]["threadId"] == "1a0783250b4df5dd"


def test_cli_thread_stdin_pipeline(mock_gmail_client):
    with patch("gmail_cli.cli.GmailClient", return_value=mock_gmail_client):
        # Pipeline stdin input
        stdin_input = "1a078384134bcbea\n1a0783250b4df5dd\n"
        res = runner.invoke(app, ["thread", "--stdin", "--json"], input=stdin_input)
        assert res.exit_code == 0
        data = json.loads(res.output)
        assert isinstance(data, list)
        assert len(data) == 2


def test_cli_message_clean_and_extract_attachments(mock_gmail_client):
    with patch("gmail_cli.cli.GmailClient", return_value=mock_gmail_client):
        res = runner.invoke(
            app,
            ["message", "1a07837b83b36bc6", "--clean", "--json"],
        )
        assert res.exit_code == 0
        data = json.loads(res.output)
        assert data["cleanBody"] == "Thank you for your email."
        assert "On Sun" in data["body"]


def test_cli_timeline_output_format(mock_gmail_client):
    with patch("gmail_cli.cli.GmailClient", return_value=mock_gmail_client):
        res = runner.invoke(app, ["timeline", "ce2fbe86"])
        assert res.exit_code == 0
        output = res.output

        # Verify timeline formatting: [YYYY-MM-DD HH:MM] Sender -> Recipient | Subject: ...
        assert (
            "[2026-09-06 19:28] Alice -> Bob | Subject: Test email ce2fbe86" in output
        )
        assert (
            "[2026-09-06 19:35] Bob -> Alice | Subject: Re: Test email ce2fbe86"
            in output
        )
        assert "[2026-09-06 19:38] Bob -> Alice | Subject: Follow-up ce2fbe86" in output
        assert "-" * 80 in output

        # Clean is default on timeline: quote stripped
        assert "Thank you for your email." in output
        assert "wrote:" not in output


def test_cli_attachment_extract_text(mock_gmail_client):
    with patch("gmail_cli.cli.GmailClient", return_value=mock_gmail_client):
        # Extract DOCX text
        res_docx = runner.invoke(
            app,
            [
                "attachment",
                "1a0783250b4df5dd",
                "Test document.docx",
                "--extract-text",
                "--json",
            ],
        )
        assert res_docx.exit_code == 0
        data_docx = json.loads(res_docx.output)
        assert "Plain text" in data_docx["extractedText"]
        assert "Row 1, Column 1" in data_docx["extractedText"]

        # Extract CSV text
        res_csv = runner.invoke(
            app,
            [
                "attachment",
                "1a0783a4a74b53f9",
                "testfile.csv",
                "--extract-text",
                "--json",
            ],
        )
        assert res_csv.exit_code == 0
        data_csv = json.loads(res_csv.output)
        assert '"Smith, Alice"' in data_csv["extractedText"]


def test_cli_text_mode_commands(mock_gmail_client):
    with patch("gmail_cli.cli.GmailClient", return_value=mock_gmail_client):
        # Text search table
        res_s = runner.invoke(app, ["search", "ce2fbe86"])
        assert res_s.exit_code == 0
        assert "Search Results for: 'ce2fbe86'" in res_s.output

        # Text search full
        res_sf = runner.invoke(app, ["search", "ce2fbe86", "--full", "--clean"])
        assert res_sf.exit_code == 0
        assert "Thread: Test email ce2fbe86" in res_sf.output

        # Text thread
        res_t = runner.invoke(
            app, ["thread", "1a078384134bcbea", "--clean", "--extract-attachments"]
        )
        assert res_t.exit_code == 0
        assert "Thread: Follow-up ce2fbe86" in res_t.output
        assert "This is a textfile test." in res_t.output

        # Text message
        res_m = runner.invoke(app, ["message", "1a07837b83b36bc6", "--clean"])
        assert res_m.exit_code == 0
        assert "Thank you for your email." in res_m.output
