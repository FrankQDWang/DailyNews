from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path


def main() -> None:
    now = datetime.now(UTC)
    day = now.strftime("%Y-%m-%d")
    out_dir = Path("docs/experiments/harness")
    out_dir.mkdir(parents=True, exist_ok=True)
    out_file = out_dir / f"{day}.md"
    if out_file.exists():
        return

    out_file.write_text(
        "\n".join(
            [
                f"# Harness Snapshot {day}",
                "",
                "## Metrics",
                "- PR lead time (median hours):",
                "- PR/day:",
                "- rollback rate:",
                "- prod bug count (P1/P2):",
                "- manual rewrite ratio:",
                "",
                "## Notes",
                "-",
            ]
        ),
        encoding="utf-8",
    )


if __name__ == "__main__":
    main()
