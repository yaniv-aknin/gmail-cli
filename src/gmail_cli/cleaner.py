import re

BOUNDARY_PATTERNS = [
    re.compile(r"^\s*-+\s*original message\s*-+", re.IGNORECASE),
    re.compile(r"^\s*-+\s*forwarded message\s*-+", re.IGNORECASE),
    re.compile(r"^\s*_{10,}\s*$"),
]

ON_WROTE_SINGLE = re.compile(r"^\s*On\s+.+?(?:wrote|writes)\s*:\s*$", re.IGNORECASE)
ON_START = re.compile(r"^\s*On\s+.+", re.IGNORECASE)
WROTE_END = re.compile(r".+?(?:wrote|writes)\s*:\s*$", re.IGNORECASE)


def clean_email_body(text: str) -> str:
    """Strip nested quoted replies and reply headers from an email body."""
    if not text:
        return ""

    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")

    # 1. Check for hard boundary headers like Original Message / Forwarded message
    for i, line in enumerate(lines):
        if any(bp.search(line) for bp in BOUNDARY_PATTERNS):
            lines = lines[:i]
            break

    # 2. Check for 'On ... wrote:' reply headers
    reply_header_idx: int | None = None
    reply_header_end: int | None = None

    for i in range(len(lines)):
        if ON_WROTE_SINGLE.match(lines[i]):
            reply_header_idx = i
            reply_header_end = i + 1
            break
        if ON_START.match(lines[i]):
            for j in range(i + 1, min(i + 4, len(lines))):
                if WROTE_END.match(lines[j]):
                    reply_header_idx = i
                    reply_header_end = j + 1
                    break
            if reply_header_idx is not None:
                break

    if reply_header_idx is not None and reply_header_end is not None:
        remainder = lines[reply_header_end:]
        has_substantive_inline_reply = False
        for rem_line in remainder:
            stripped = rem_line.strip()
            if not stripped or stripped.startswith((">", "&gt;")):
                continue
            has_substantive_inline_reply = True
            break

        if not has_substantive_inline_reply:
            lines = lines[:reply_header_idx]
        else:
            lines = lines[:reply_header_idx] + lines[reply_header_end:]

    # 3. Filter out lines starting with '>' or '&gt;'
    cleaned_lines = [l for l in lines if not l.strip().startswith((">", "&gt;"))]

    return "\n".join(cleaned_lines).strip()
