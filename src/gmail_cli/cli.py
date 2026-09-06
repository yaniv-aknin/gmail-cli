import json
import sys
import time
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import requests
import typer

from gmail_cli.auth import (
    find_token_cache_path,
    load_token_cache,
    perform_interactive_oauth,
)
from gmail_cli.client import GmailClient
from gmail_cli.documents import extract_attachment_text
from gmail_cli.formatting import (
    console,
    error_console,
    format_byte_size,
    format_duration,
    render_message_panel,
    render_search_table,
    render_thread_panel,
    render_timeline_message,
)
from gmail_cli.parser import (
    decode_base64url,
    extract_headers,
    parse_message_payload,
    parse_mime_tree,
)
from gmail_cli.timeline import build_timeline, extract_attachments_for_messages

app = typer.Typer(
    name="gmail-cli",
    help="CLI tool to search Gmail, read email threads, and manage attachments.",
    add_completion=False,
)
auth_app = typer.Typer(
    name="auth",
    help="Manage authentication and token status.",
    no_args_is_help=True,
)
app.add_typer(auth_app, name="auth")


def _collect_thread_ids(
    thread_ids: list[str] | None, stdin_flag: bool
) -> tuple[list[str], bool]:
    ids_to_fetch: list[str] = []
    read_from_stdin = stdin_flag

    if thread_ids:
        for tid in thread_ids:
            if tid == "-":
                read_from_stdin = True
            else:
                ids_to_fetch.append(tid)

    if read_from_stdin or (not ids_to_fetch and not sys.stdin.isatty()):
        read_from_stdin = True
        raw_input = sys.stdin.read().strip()
        if raw_input:
            try:
                parsed_json = json.loads(raw_input)
                if isinstance(parsed_json, dict) and "threads" in parsed_json:
                    for item in parsed_json["threads"]:
                        tid = item.get("threadId") or item.get("id")
                        if tid:
                            ids_to_fetch.append(str(tid))
                elif isinstance(parsed_json, list):
                    for item in parsed_json:
                        if isinstance(item, dict):
                            tid = item.get("threadId") or item.get("id")
                            if tid:
                                ids_to_fetch.append(str(tid))
                        elif isinstance(item, str) and item.strip():
                            ids_to_fetch.append(item.strip())
                elif isinstance(parsed_json, str) and parsed_json.strip():
                    ids_to_fetch.append(parsed_json.strip())
            except json.JSONDecodeError:
                for line in raw_input.splitlines():
                    clean_line = line.strip()
                    if clean_line:
                        ids_to_fetch.append(clean_line)

    return list(dict.fromkeys(ids_to_fetch)), read_from_stdin


def _download_attachments_to_dir(
    client: GmailClient,
    messages: list[dict[str, Any]],
    download_dir: Path,
) -> list[str]:
    downloaded_attachments: list[str] = []
    download_dir.mkdir(parents=True, exist_ok=True)
    for msg in messages:
        for attachment_info in msg.get("attachments", []):
            filename = attachment_info["filename"]
            attachment_id = attachment_info["attachmentId"]
            message_id = attachment_info["messageId"]

            if attachment_id:
                file_bytes = client.get_attachment(message_id, attachment_id)
            elif attachment_info.get("inlineData"):
                file_bytes = decode_base64url(attachment_info["inlineData"])
            else:
                continue

            destination = download_dir / f"{message_id}_{filename}"
            with open(destination, "wb") as file:
                file.write(file_bytes)
            downloaded_attachments.append(str(destination))
            attachment_info["savedTo"] = str(destination)
    return downloaded_attachments


@auth_app.command("login")
def auth_login(
    force: bool = typer.Option(
        False,
        "--force",
        "-f",
        help="Force re-authentication even if current token is valid.",
    ),
    no_browser: bool = typer.Option(
        False,
        "--no-browser",
        help="Print authorization URL instead of opening browser.",
    ),
    print_token: bool = typer.Option(
        False, "--print-token", "-t", help="Print access token after authentication."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output token details as JSON."
    ),
) -> None:
    """Explicitly authenticate with Gmail via OAuth."""
    cached_token = load_token_cache()
    if not force and cached_token:
        access_token = cached_token.get("access_token")
        expires_at = cached_token.get("expires_at", 0)
        if access_token and time.time() < (expires_at - 60):
            if json_output:
                print(json.dumps(cached_token, indent=2))
                return
            if print_token:
                print(access_token)
            else:
                console.print(
                    "[bold green]Already authenticated with a valid token.[/bold green] Use '--force' to re-login."
                )
            return

    token = perform_interactive_oauth(open_browser=not no_browser)

    if json_output:
        token_info = load_token_cache() or {"access_token": token}
        print(json.dumps(token_info, indent=2))
        return

    if print_token or no_browser:
        print(token)
    else:
        console.print(
            "[bold green]Authentication successful. Token is active.[/bold green]"
        )


@auth_app.command("status")
def auth_status(
    json_output: bool = typer.Option(
        False, "--json", help="Output status details as JSON."
    ),
) -> None:
    """Check authentication status and remaining token validity."""
    cache_path = find_token_cache_path()
    cached_token = load_token_cache()

    if not cached_token or not cached_token.get("access_token"):
        if json_output:
            print(
                json.dumps(
                    {
                        "authenticated": False,
                        "token_file": str(cache_path) if cache_path.exists() else None,
                        "message": "No access token found",
                    },
                    indent=2,
                )
            )
            return
        console.print("[yellow]No access token found.[/yellow]")
        console.print(f"Token file: {cache_path}")
        console.print("Run '[bold cyan]gmail auth login[/bold cyan]' to authenticate.")
        return

    expires_at = cached_token.get("expires_at")
    now = time.time()

    if expires_at is None and "expires_in" in cached_token and cache_path.exists():
        expires_at = cache_path.stat().st_mtime + float(cached_token["expires_in"])

    if expires_at is None:
        if json_output:
            print(
                json.dumps(
                    {
                        "authenticated": True,
                        "active": True,
                        "token_file": str(cache_path),
                        "expires_at": None,
                        "message": "Token found, but expiration timestamp is not recorded",
                    },
                    indent=2,
                )
            )
            return
        console.print(
            "[bold green]Token is present.[/bold green] Expiration time unknown."
        )
        console.print(f"Token file: {cache_path}")
        return

    time_left = expires_at - now
    expires_dt = datetime.fromtimestamp(expires_at, tz=UTC)
    expires_iso = expires_dt.isoformat()
    expires_str = expires_dt.strftime("%Y-%m-%d %H:%M:%S UTC")
    verbose_time, short_time = format_duration(time_left)

    if time_left > 0:
        if json_output:
            print(
                json.dumps(
                    {
                        "authenticated": True,
                        "active": True,
                        "expired": False,
                        "seconds_remaining": round(time_left, 1),
                        "time_remaining_formatted": short_time,
                        "expires_at": expires_at,
                        "expires_at_iso": expires_iso,
                        "token_file": str(cache_path),
                    },
                    indent=2,
                )
            )
            return

        console.print("[bold green]Token is active.[/bold green]")
        console.print(
            f"Time left: [bold cyan]{verbose_time}[/bold cyan] ({short_time})"
        )
        console.print(f"Expires at: {expires_str}")
        console.print(f"Token file: {cache_path}")
    else:
        if json_output:
            print(
                json.dumps(
                    {
                        "authenticated": True,
                        "active": False,
                        "expired": True,
                        "seconds_expired_ago": round(abs(time_left), 1),
                        "expired_ago_formatted": short_time,
                        "expires_at": expires_at,
                        "expires_at_iso": expires_iso,
                        "token_file": str(cache_path),
                    },
                    indent=2,
                )
            )
            return

        console.print("[bold red]Token is expired.[/bold red]")
        console.print(
            f"Expired: [bold yellow]{verbose_time} ago[/bold yellow] ({short_time} ago)"
        )
        console.print(f"Expired at: {expires_str}")
        console.print(f"Token file: {cache_path}")
        console.print(
            "Run '[bold cyan]gmail auth login[/bold cyan]' to re-authenticate."
        )


@app.command()
def search(
    query: str = typer.Argument(..., help="Gmail search query string."),
    limit: int = typer.Option(20, "--limit", "-l", help="Maximum threads to return."),
    page_token: str | None = typer.Option(
        None, "--page-token", "-p", help="Pagination token."
    ),
    include_spam_trash: bool = typer.Option(
        False, "--include-spam-trash", help="Include Spam and Trash."
    ),
    full: bool = typer.Option(
        False,
        "--full",
        "--include-messages",
        help="Include full message details and bodies.",
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        "--no-quotes",
        help="Strip nested quoted replies and reply headers in full output.",
    ),
    extract_attachments: bool = typer.Option(
        False,
        "--extract-attachments",
        "--extract-text",
        help="Extract attachment text in full output.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output machine-readable JSON."
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Disable automatic browser opening for auth."
    ),
) -> None:
    """Search email threads matching a Gmail query."""
    client = GmailClient(allow_browser=not no_browser)
    raw_response = client.search_threads(
        query=query,
        limit=limit,
        page_token=page_token,
        include_spam_trash=include_spam_trash,
    )
    thread_items = raw_response.get("threads", [])

    thread_results = []
    for item in thread_items:
        thread_id = item["id"]
        try:
            full_thread = client.get_thread(thread_id, format_type="full")
            raw_messages = full_thread.get("messages", [])
            if not raw_messages:
                continue

            first_headers = extract_headers(raw_messages[0].get("payload", {}))
            last_headers = extract_headers(raw_messages[-1].get("payload", {}))
            senders = list(
                dict.fromkeys(
                    extract_headers(msg.get("payload", {})).get("from", "Unknown")
                    for msg in raw_messages
                )
            )
            attachment_count = sum(
                len(parse_mime_tree(msg.get("payload", {}), msg.get("id", ""))[2])
                for msg in raw_messages
            )

            result_entry: dict[str, Any] = {
                "threadId": thread_id,
                "subject": first_headers.get("subject", "(No Subject)"),
                "messageCount": len(raw_messages),
                "senders": senders,
                "startDate": first_headers.get("date", ""),
                "lastDate": last_headers.get("date", ""),
                "snippet": raw_messages[-1].get("snippet", ""),
                "attachmentCount": attachment_count,
            }

            if full:
                parsed_messages = [parse_message_payload(msg) for msg in raw_messages]
                if extract_attachments:
                    extract_attachments_for_messages(client, parsed_messages)
                result_entry["messages"] = parsed_messages

            thread_results.append(result_entry)
        except (requests.RequestException, RuntimeError, KeyError) as error:
            thread_results.append(
                {
                    "threadId": thread_id,
                    "snippet": item.get("snippet", ""),
                    "error": str(error),
                }
            )

    output_payload = {
        "query": query,
        "resultCount": len(thread_results),
        "nextPageToken": raw_response.get("nextPageToken"),
        "threads": thread_results,
    }

    if json_output:
        print(json.dumps(output_payload, indent=2))
        return

    if not thread_results:
        console.print(f"[yellow]No threads found matching: '{query}'[/yellow]")
        return

    if full:
        for t_info in thread_results:
            if "messages" in t_info:
                render_thread_panel(
                    console,
                    t_info,
                    clean=clean,
                    extract_attachments=extract_attachments,
                )
        return

    render_search_table(console, query, thread_results)


@app.command()
def thread(
    thread_ids: list[str] = typer.Argument(
        None, help="One or more Thread IDs to fetch."
    ),
    clean: bool = typer.Option(
        False,
        "--clean",
        "--no-quotes",
        help="Strip nested quoted replies and reply headers.",
    ),
    extract_attachments: bool = typer.Option(
        False,
        "--extract-attachments",
        "--extract-text",
        help="Extract and display attachment text inline.",
    ),
    stdin: bool = typer.Option(False, "--stdin", help="Read thread ID(s) from stdin."),
    download_dir: Path | None = typer.Option(
        None, "--download-attachments", "-d", help="Directory to save attachments."
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output machine-readable JSON."
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Disable automatic browser opening for auth."
    ),
) -> None:
    """Read email thread(s) with all messages and attachment metadata."""
    target_ids, was_stdin = _collect_thread_ids(thread_ids, stdin)

    if not target_ids:
        error_console.print("[bold red]Error: No thread ID provided.[/bold red]")
        raise typer.Exit(code=1)

    client = GmailClient(allow_browser=not no_browser)
    thread_summaries = []

    for thread_id in target_ids:
        try:
            raw_thread = client.get_thread(thread_id, format_type="full")
            parsed_messages = [
                parse_message_payload(msg) for msg in raw_thread.get("messages", [])
            ]

            if extract_attachments:
                extract_attachments_for_messages(client, parsed_messages)

            downloaded = []
            if download_dir:
                downloaded = _download_attachments_to_dir(
                    client, parsed_messages, download_dir
                )

            summary = {
                "threadId": thread_id,
                "messageCount": len(parsed_messages),
                "subject": (
                    parsed_messages[0]["subject"] if parsed_messages else "(No Subject)"
                ),
                "messages": parsed_messages,
                "downloadedAttachments": downloaded,
            }
            thread_summaries.append(summary)
        except (
            requests.RequestException,
            RuntimeError,
            KeyError,
            OSError,
            ValueError,
        ) as error:
            thread_summaries.append(
                {
                    "threadId": thread_id,
                    "error": str(error),
                }
            )

    is_batch = was_stdin or (thread_ids is not None and len(thread_ids) > 1)

    if json_output:
        if not is_batch and len(thread_summaries) == 1:
            print(json.dumps(thread_summaries[0], indent=2))
        else:
            print(json.dumps(thread_summaries, indent=2))
        return

    for t_summary in thread_summaries:
        if "error" in t_summary:
            error_console.print(
                f"[bold red]Error fetching thread {t_summary['threadId']}: {t_summary['error']}[/bold red]"
            )
            continue

        render_thread_panel(
            console,
            t_summary,
            clean=clean,
            extract_attachments=extract_attachments,
        )
        if t_summary.get("downloadedAttachments"):
            console.print(
                f"[bold green]Saved {len(t_summary['downloadedAttachments'])} attachment(s) to {download_dir}[/bold green]"
            )


@app.command()
def message(
    message_id: str = typer.Argument(..., help="Message ID to fetch."),
    clean: bool = typer.Option(
        False,
        "--clean",
        "--no-quotes",
        help="Strip nested quoted replies and reply headers.",
    ),
    extract_attachments: bool = typer.Option(
        False,
        "--extract-attachments",
        "--extract-text",
        help="Extract and display attachment text inline.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output machine-readable JSON."
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Disable automatic browser opening for auth."
    ),
) -> None:
    """Read a single email message by ID."""
    client = GmailClient(allow_browser=not no_browser)
    raw_message = client.get_message(message_id, format_type="full")
    parsed_message = parse_message_payload(raw_message)

    if extract_attachments:
        extract_attachments_for_messages(client, [parsed_message])

    if json_output:
        print(json.dumps(parsed_message, indent=2))
        return

    render_message_panel(
        console,
        parsed_message,
        clean=clean,
        extract_attachments=extract_attachments,
    )


@app.command()
def timeline(
    query: str = typer.Argument(..., help="Gmail search query string."),
    limit: int = typer.Option(
        50, "--limit", "-l", help="Maximum messages to return (default: 50)."
    ),
    since: str | None = typer.Option(
        None,
        "--since",
        "--after",
        help="Filter messages after a date (YYYY-MM-DD or timestamp).",
    ),
    until: str | None = typer.Option(
        None,
        "--until",
        "--before",
        help="Filter messages before a date (YYYY-MM-DD or timestamp).",
    ),
    clean: bool = typer.Option(
        True,
        "--clean/--no-clean",
        "--no-quotes/--quotes",
        help="Strip quoted historical chains (default: True).",
    ),
    extract_attachments: bool = typer.Option(
        False,
        "--extract-attachments",
        "--extract-text",
        help="Extract and display attachment text inline.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output machine-readable JSON."
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Disable automatic browser opening for auth."
    ),
) -> None:
    """Flatten messages across matching threads into a chronological timeline."""
    client = GmailClient(allow_browser=not no_browser)
    timeline_messages, errors = build_timeline(
        client=client,
        query=query,
        limit=limit,
        since=since,
        until=until,
        extract_attachments=extract_attachments,
    )

    for err in errors:
        error_console.print(f"[dim yellow]Warning: {err}[/dim yellow]")

    if json_output:
        print(json.dumps(timeline_messages, indent=2))
        return

    if not timeline_messages:
        console.print(
            f"[yellow]No messages found matching timeline criteria: '{query}'[/yellow]"
        )
        return

    for msg in timeline_messages:
        render_timeline_message(
            console,
            msg,
            clean=clean,
            extract_attachments=extract_attachments,
        )


@app.command()
def attachment(
    message_id: str = typer.Argument(..., help="Message ID containing attachment."),
    attachment_id: str = typer.Argument(..., help="Attachment ID or filename."),
    output_path: Path | None = typer.Option(
        None, "--output", "-o", help="Path to save file."
    ),
    read_text: bool = typer.Option(
        False,
        "--text",
        "-t",
        "--extract-text",
        help="Extract and display text content.",
    ),
    json_output: bool = typer.Option(
        False, "--json", help="Output machine-readable JSON."
    ),
    no_browser: bool = typer.Option(
        False, "--no-browser", help="Disable automatic browser opening for auth."
    ),
) -> None:
    """Download or extract text from an email attachment."""
    client = GmailClient(allow_browser=not no_browser)
    raw_message = client.get_message(message_id, format_type="full")
    parsed_message = parse_message_payload(raw_message)

    target_id = attachment_id
    filename = attachment_id
    mime_type = "application/octet-stream"

    for att in parsed_message.get("attachments", []):
        if att["attachmentId"] == attachment_id or att["filename"] == attachment_id:
            target_id = att["attachmentId"]
            filename = att["filename"]
            mime_type = att["mimeType"]
            break

    if not target_id:
        error_console.print(
            f"[bold red]Attachment '{attachment_id}' not found in message {message_id}[/bold red]"
        )
        sys.exit(1)

    file_bytes = client.get_attachment(message_id, target_id)

    saved_location = None
    if output_path:
        destination = output_path / filename if output_path.is_dir() else output_path
        destination.parent.mkdir(parents=True, exist_ok=True)
        with open(destination, "wb") as file:
            file.write(file_bytes)
        saved_location = str(destination)

    extracted_text = (
        extract_attachment_text(filename, mime_type, file_bytes)
        if (read_text or json_output)
        else None
    )

    if json_output:
        result_payload = {
            "messageId": message_id,
            "attachmentId": target_id,
            "filename": filename,
            "mimeType": mime_type,
            "sizeBytes": len(file_bytes),
            "savedTo": saved_location,
            "extractedText": extracted_text,
        }
        print(json.dumps(result_payload, indent=2))
        return

    if saved_location:
        console.print(f"[bold green]Saved attachment to:[/bold green] {saved_location}")

    if read_text:
        if extracted_text is not None:
            from rich.panel import Panel

            console.print(
                Panel(
                    f"[bold]Attachment Content:[/bold] {filename} ({format_byte_size(len(file_bytes))})",
                    border_style="yellow",
                )
            )
            console.print(extracted_text)
        else:
            console.print(
                f"[yellow]Attachment '{filename}' is binary ({mime_type}) and cannot be displayed as text.[/yellow]"
            )
