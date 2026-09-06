import email.utils
from datetime import UTC, datetime
from typing import Any

from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()
error_console = Console(stderr=True)


def format_duration(seconds: float) -> tuple[str, str]:
    """Format duration in seconds into verbose and short human-readable strings."""
    total_seconds = int(abs(seconds))
    hours, remainder = divmod(total_seconds, 3600)
    minutes, secs = divmod(remainder, 60)

    short_parts = []
    if hours > 0:
        short_parts.append(f"{hours}h")
    if minutes > 0 or hours > 0:
        short_parts.append(f"{minutes}m")
    short_parts.append(f"{secs}s")
    short_str = " ".join(short_parts)

    verbose_parts = []
    if hours > 0:
        verbose_parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if minutes > 0:
        verbose_parts.append(f"{minutes} minute{'s' if minutes != 1 else ''}")
    if secs > 0 or not verbose_parts:
        verbose_parts.append(f"{secs} second{'s' if secs != 1 else ''}")
    verbose_str = ", ".join(verbose_parts)

    return verbose_str, short_str


def format_byte_size(total_bytes: int) -> str:
    """Format a byte count into a human-readable size string."""
    current_size = float(total_bytes)
    for unit in ["B", "KB", "MB", "GB"]:
        if current_size < 1024.0:
            return (
                f"{current_size:.1f} {unit}"
                if unit != "B"
                else f"{int(current_size)} B"
            )
        current_size /= 1024.0
    return f"{current_size:.1f} TB"


def format_contact_name(contact: str) -> str:
    """Extract human-readable name or email from a contact string like 'Name <email>'."""
    if not contact:
        return "(Unknown)"
    addresses = email.utils.getaddresses([contact])
    names = []
    for display_name, email_addr in addresses:
        clean_name = display_name.strip().strip("\"'")
        if clean_name:
            names.append(clean_name)
        elif email_addr:
            names.append(email_addr)
    return ", ".join(names) if names else contact.strip()


def render_search_table(
    render_console: Console, query: str, thread_results: list[dict[str, Any]]
) -> None:
    """Render a Rich summary table of search results."""
    table = Table(
        title=f"Search Results for: '{query}' ({len(thread_results)} threads)",
        show_lines=True,
    )
    table.add_column("Thread ID", style="cyan", no_wrap=True)
    table.add_column("Subject", style="bold white", min_width=24)
    table.add_column("Msgs", justify="center", style="magenta", width=6)
    table.add_column("Senders", style="green", min_width=16)
    table.add_column("Last Date", style="blue", no_wrap=True)
    table.add_column("Att.", justify="center", style="yellow", width=5)

    for item in thread_results:
        formatted_senders = ", ".join(
            sender.split("<")[0].strip() for sender in item.get("senders", [])
        )
        table.add_row(
            item.get("threadId", ""),
            item.get("subject", ""),
            str(item.get("messageCount", "")),
            formatted_senders,
            item.get("lastDate", ""),
            str(item.get("attachmentCount", 0)) if item.get("attachmentCount") else "-",
        )

    render_console.print(table)


def render_message_panel(
    render_console: Console,
    msg: dict[str, Any],
    index: int | None = None,
    total: int | None = None,
    clean: bool = False,
    extract_attachments: bool = False,
) -> None:
    """Render a single email message in a Rich panel with headers, body, and attachments."""
    headers_table = Table(show_header=False, box=None, padding=(0, 1))
    headers_table.add_column("Field", style="bold cyan", width=10)
    headers_table.add_column("Value")
    headers_table.add_row("Date:", msg.get("date", ""))
    headers_table.add_row("From:", msg.get("from", ""))
    if msg.get("to"):
        headers_table.add_row("To:", msg["to"])
    if msg.get("cc"):
        headers_table.add_row("CC:", msg["cc"])
    headers_table.add_row("Subject:", msg.get("subject", ""))
    headers_table.add_row("Msg ID:", f"[dim]{msg.get('id', '')}[/dim]")

    title = (
        f"Message {index}/{total}"
        if index is not None and total is not None
        else f"Message ID: {msg.get('id', '')}"
    )
    render_console.print(
        Panel(headers_table, title=title, border_style="blue", expand=True)
    )

    body_content = msg.get("cleanBody") if clean else msg.get("body", "")
    if not body_content:
        body_content = "(Empty message body)"
    render_console.print(body_content)

    if msg.get("attachments"):
        render_console.print("\n[bold yellow]Attachments:[/bold yellow]")
        for att in msg["attachments"]:
            render_console.print(
                f"📎 [bold]{att['filename']}[/bold] ({att['mimeType']}, {format_byte_size(att['sizeBytes'])}) -> ID: [cyan]{att['attachmentId']}[/cyan]"
            )
            if extract_attachments and att.get("extractedText"):
                render_console.print(
                    Panel(
                        att["extractedText"],
                        title=f"Extracted Text: {att['filename']}",
                        border_style="yellow",
                    )
                )
    render_console.print("-" * 80)


def render_thread_panel(
    render_console: Console,
    thread_summary: dict[str, Any],
    clean: bool = False,
    extract_attachments: bool = False,
) -> None:
    """Render an entire email thread panel and all of its messages."""
    first_subject = thread_summary.get("subject", "(No Subject)")
    thread_id = thread_summary.get("threadId", "")
    parsed_messages = thread_summary.get("messages", [])

    render_console.print(
        Panel(
            f"[bold]Thread:[/bold] {first_subject}\n[dim]ID: {thread_id} | {len(parsed_messages)} message(s)[/dim]",
            border_style="cyan",
        )
    )

    for index, msg in enumerate(parsed_messages, 1):
        render_message_panel(
            render_console,
            msg,
            index=index,
            total=len(parsed_messages),
            clean=clean,
            extract_attachments=extract_attachments,
        )


def render_timeline_message(
    render_console: Console,
    msg: dict[str, Any],
    clean: bool = True,
    extract_attachments: bool = False,
) -> None:
    """Render a message in the timeline format."""
    ts = msg.get("timestamp")
    if ts:
        dt = datetime.fromtimestamp(ts, tz=UTC)
        formatted_date = dt.strftime("%Y-%m-%d %H:%M")
    else:
        formatted_date = msg.get("date", "")[:16]

    sender_name = format_contact_name(msg.get("from", "Unknown"))
    recipient_name = format_contact_name(msg.get("to", "Unknown"))
    subject = msg.get("subject", "(No Subject)")
    thread_id = msg.get("threadId", "")

    render_console.print(
        f"[{formatted_date}] {sender_name} -> {recipient_name} | Subject: {subject} (Thread: {thread_id})",
        soft_wrap=True,
    )
    render_console.print("-" * 80)
    body_text = msg.get("cleanBody") if clean else msg.get("body", "")
    if not body_text:
        body_text = "(Empty message body)"
    render_console.print(body_text)

    if msg.get("attachments"):
        render_console.print("\n[bold yellow]Attachments:[/bold yellow]")
        for att in msg["attachments"]:
            render_console.print(
                f"📎 [bold]{att['filename']}[/bold] ({att['mimeType']}, {format_byte_size(att['sizeBytes'])})"
            )
            if extract_attachments and att.get("extractedText"):
                render_console.print(
                    Panel(
                        att["extractedText"],
                        title=f"Extracted Text: {att['filename']}",
                        border_style="yellow",
                    )
                )
    render_console.print()
