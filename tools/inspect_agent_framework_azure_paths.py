from __future__ import annotations

import re
from pathlib import Path


def main() -> int:
    try:
        import agent_framework  # type: ignore
    except Exception as exc:  # pragma: no cover
        print("Failed to import agent_framework:", exc)
        return 2

    root = Path(agent_framework.__file__).resolve().parent / "azure"
    print("agent_framework.azure dir:", root)
    if not root.exists():
        print("Not found")
        return 2

    patterns = [
        r"/openai/[a-zA-Z0-9_\-\/{}]+",
        r"openai/[a-zA-Z0-9_\-\/{}]+",
        r"api-version",
        r"responses",
        r"chat/completions",
    ]

    compiled = [re.compile(p) for p in patterns]

    hits = []
    for py in sorted(root.rglob("*.py")):
        text = py.read_text(encoding="utf-8", errors="ignore")
        if any(c.search(text) for c in compiled):
            hits.append(py)

    print("Files with potential URL/path hints:")
    for p in hits:
        print(" -", p)

    print("\nRelevant lines:")
    for p in hits:
        lines = p.read_text(encoding="utf-8", errors="ignore").splitlines()
        printed_header = False
        for i, line in enumerate(lines, 1):
            if (
                "openai" in line
                or "api-version" in line
                or "responses" in line
                or "chat/completions" in line
                or "/deployments" in line
            ):
                if not printed_header:
                    print("\nFILE", p)
                    printed_header = True
                print(f"{i:>4}: {line[:220]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
