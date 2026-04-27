from pathlib import Path


def resolve_body_source(positional, from_file):
    """Pick exactly one source and return the body text."""
    if positional is not None and from_file:
        raise ValueError("positional body and --from-file are mutually exclusive")
    if positional is not None:
        if positional == "":
            raise ValueError("body is empty")
        return positional
    if from_file:
        try:
            return Path(from_file).read_text()
        except OSError as exc:
            raise ValueError(f"cannot read {from_file}: {exc}") from exc
    raise ValueError("body is required: pass as positional arg or --from-file PATH")


def format_comment(c):
    """Format a jira.Comment or dict-like into the display form from spec."""
    created = c["created"] if isinstance(c, dict) else c.created
    author = (c["author"]["displayName"] if isinstance(c, dict) else c.author.displayName)
    body = c["body"] if isinstance(c, dict) else c.body
    cid = c["id"] if isinstance(c, dict) else c.id
    # created like "2026-04-23T20:59:12.000+0300" → "2026-04-23 20:59"
    date_part, time_part = created.split("T")
    hhmm = time_part[:5]
    header = f"[{date_part} {hhmm}] {author} (id={cid}):"
    return f"{header}\n{body}\n---\n"
