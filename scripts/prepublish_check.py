#!/usr/bin/env python3
from pathlib import Path
import re
import sys

ROOT = Path(sys.argv[1] if len(sys.argv) > 1 else ".").resolve()

SKIP_DIRS = {
    ".git", ".venv", "venv", "build", "dist",
    "__pycache__", ".pytest_cache", ".mypy_cache",
}

BAD_FILE_PATTERNS = [
    re.compile(r"\.(?:db|sqlite|sqlite3)$", re.I),
    re.compile(r"\.bak", re.I),
    re.compile(r"\.(?:new|download|dmp)$", re.I),
]

SECRET_PATTERNS = [
    ("generic secret assignment", re.compile(
        r"""(?ix)
        \b(?:api[_-]?key|token|secret|password)\b
        \s*=\s*
        ["'][^"'\n]{8,}["']
        """
    )),
    ("OpenAI/OpenRouter-like key", re.compile(r"\bsk-[A-Za-z0-9_-]{20,}\b")),
    ("GitHub token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{20,}\b")),
    ("JWT", re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\b")),
]

IP_ASSIGN = re.compile(
    r"""(?im)^\s*SERVER_IP\s*=\s*["'](?!127\.0\.0\.1|0\.0\.0\.0|localhost)(\d{1,3}(?:\.\d{1,3}){3})["']"""
)

PRIVATE_PATH = re.compile(r"""(?i)(?:[A-Z]:\\Users\\|[A-Z]:\\[^"' \n]{2,}|/home/[^/"' \n]+/)""")

TEXT_EXT = {
    ".py", ".md", ".txt", ".json", ".toml", ".yaml", ".yml",
    ".ini", ".cfg", ".ps1", ".bat", ".cmd", ".html", ".css", ".js"
}

errors = []
warnings = []

for path in ROOT.rglob("*"):
    if not path.is_file():
        continue
    if any(part in SKIP_DIRS for part in path.parts):
        continue

    rel = path.relative_to(ROOT)

    if any(p.search(path.name) for p in BAD_FILE_PATTERNS):
        errors.append(f"private/runtime file: {rel}")
        continue

    if path.name in {"chat_users.db", ".env", "secrets.json", "client_crash.txt"}:
        errors.append(f"private/runtime file: {rel}")
        continue

    if path.suffix.lower() in {".mp3", ".wav", ".m4a", ".aac", ".ogg"}:
        warnings.append(f"audio license check: {rel}")

    if path.suffix.lower() not in TEXT_EXT:
        continue

    try:
        text = path.read_text(encoding="utf-8", errors="ignore")
    except Exception:
        continue

    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(f"{label}: {rel}")

    if IP_ASSIGN.search(text):
        errors.append(f"hardcoded SERVER_IP: {rel}")

    if PRIVATE_PATH.search(text):
        warnings.append(f"possible local path: {rel}")

print(f"BUKKAX pre-publish check: {ROOT}")

if warnings:
    print("\nWARNINGS:")
    for item in sorted(set(warnings)):
        print("  -", item)

if errors:
    print("\nERRORS:")
    for item in sorted(set(errors)):
        print("  -", item)
    print("\nFAILED: do not publish yet.")
    raise SystemExit(1)

print("\nOK: no blocking findings.")
