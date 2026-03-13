from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class ParsedCommand:
    name: str
    arg: str | None


def parse_command(text: str) -> ParsedCommand | None:
    raw = text.strip()
    if not raw.startswith("/"):
        return None
    parts = raw.split(maxsplit=1)
    cmd = parts[0][1:]
    cmd = cmd.split("@", maxsplit=1)[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else None
    return ParsedCommand(name=cmd, arg=arg)
