#!/usr/bin/env python3
"""Confidentiality denylist for the gate. Standard library only.

Scans the files git would commit for Rosters, transcript/Flag exports, an
Install's network details, and unfilled-in template fields, as specified in
docs/research/pii-scan.md. See scripts/confidentiality-waivers.toml for the
waiver format.
"""

from __future__ import annotations

import argparse
import fnmatch
import hashlib
import ipaddress
import re
import subprocess
import sys
import tomllib
from pathlib import Path

STRONG_NAME_HEADERS = {
    "student",
    "student name",
    "first name",
    "last name",
    "surname",
    "given name",
    "full name",
    "pupil",
    "legal name",
}
WEAK_NAME_HEADERS = {"name"}
CARD_HEADERS = {"card", "card number"}


def has_roster_header(folded_columns: list[str]) -> bool:
    if any(c in STRONG_NAME_HEADERS for c in folded_columns):
        return True
    has_weak_name = any(c in WEAK_NAME_HEADERS for c in folded_columns)
    has_card = any(c in CARD_HEADERS for c in folded_columns)
    return has_weak_name and has_card


TEMPLATE_FIELD_HEADERS = {"name", "signature", "student", "staff", "contact"}

TEMPLATE_LABELS = (
    "Prepared by",
    "Legal review",
    "Approved by",
    "Signed",
    "Superintendent",
    "School Board",
)

SPREADSHEET_EXTENSIONS = {".xlsx", ".xls", ".ods", ".numbers"}
BINARY_EXTENSIONS = SPREADSHEET_EXTENSIONS | {
    ".sqlite",
    ".sqlite3",
    ".db",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".pdf",
}

EXPORT_FILENAME_GLOBS = (
    "*transcript*",
    "*flag-export*",
    "*flags*.json",
    "*flags*.jsonl",
    "*flags*.csv",
    "*.sqlite*",
    "*.db",
)

BLANK_RE = re.compile(r"^\[BLANK(: [^\]]*)?\]$")
TABLE_ROW_RE = re.compile(r"^\s*\|(.*)\|\s*$")
TABLE_SEP_RE = re.compile(r"^\s*\|[\s:|-]+\|\s*$")

IPV4_RE = re.compile(r"\b(?:\d{1,3}\.){3}\d{1,3}(?:/\d{1,2})?\b")
IPV6_RE = re.compile(r"\b[0-9a-fA-F]{1,4}(?::[0-9a-fA-F]{0,4}){2,7}(?:/\d{1,3})?\b")

DOC_NETWORKS = [
    ipaddress.ip_network("192.0.2.0/24"),
    ipaddress.ip_network("198.51.100.0/24"),
    ipaddress.ip_network("203.0.113.0/24"),
    ipaddress.ip_network("2001:db8::/32"),
]

NETWORK_CONFIG_PATTERNS = [
    re.compile(r"\bvlan\s+(?:id\s+)?\d+\b", re.IGNORECASE),
    re.compile(r"\bswitchport\s+(?:access|mode|trunk)\b", re.IGNORECASE),
    re.compile(r"\biptables\s+-[AI]\s+[A-Z]+\b"),
    re.compile(r"\bnft\s+add\s+rule\s+\S+"),
    re.compile(r"\btable\s+inet\s+[a-zA-Z_]\w*"),
    re.compile(r"\baccess-list\s+\d+\b", re.IGNORECASE),
    re.compile(r"\bufw\s+(?:allow|deny)\s+\S+", re.IGNORECASE),
    re.compile(r"\b(?:[0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}\b"),
    re.compile(r"\b[\w-]+\.(?:lan|local|internal|corp|home\.arpa)\b", re.IGNORECASE),
]

EMAIL_RE = re.compile(r"\b[A-Za-z0-9._%+-]+@([A-Za-z0-9.-]+\.[A-Za-z]{2,})\b")
RESERVED_EMAIL_DOMAINS = re.compile(
    r"(?:^|\.)(?:example\.com|example\.org|example\.net|example|test|invalid)$",
    re.IGNORECASE,
)

HONORIFIC_RE = re.compile(r"\b(?:Mr|Mrs|Ms|Miss|Mx|Dr)\.?\s+[A-Z][a-z]+\b")

GITLEAKS_ALLOW = "gitleaks" + ":allow"

REQUIRED_WAIVER_KEYS = {"path", "rule", "sha256", "bead", "reason"}


def fold_header(cell: str) -> str:
    cell = cell.strip().strip("`").strip()
    cell = re.sub(r"[^a-z0-9 ]", "", cell.lower())
    return re.sub(r"\s+", " ", cell).strip()


def strip_blank_value(cell: str) -> str:
    return cell.strip().strip("`").strip()


def is_blank(cell: str) -> bool:
    value = strip_blank_value(cell)
    return value == "" or bool(BLANK_RE.match(value))


def split_row(row: str) -> list[str]:
    return [c.strip() for c in row.strip().strip("|").split("|")]


def find_tables(lines: list[str]):
    """Yield (header_line_no, header_cells, [(line_no, cells), ...]) for each table."""
    i = 0
    n = len(lines)
    while i < n - 1:
        header_match = TABLE_ROW_RE.match(lines[i])
        sep_match = TABLE_SEP_RE.match(lines[i + 1]) if header_match else None
        if header_match and sep_match:
            header_cells = split_row(lines[i])
            rows = []
            j = i + 2
            while j < n and TABLE_ROW_RE.match(lines[j]):
                rows.append((j + 1, split_row(lines[j])))
                j += 1
            yield (i + 1, header_cells, rows)
            i = j
        else:
            i += 1


def check_roster_csv(path: Path, rel: str, text: str) -> list[tuple[int, str, str]]:
    delimiter = "\t" if path.suffix.lower() == ".tsv" else ","
    first_line = text.splitlines()[0] if text.splitlines() else ""
    columns = [fold_header(c) for c in first_line.split(delimiter)]
    if has_roster_header(columns):
        return [(1, "roster-csv", "Roster file header detected")]
    return []


def check_roster_table(rel: str, lines: list[str]) -> list[tuple[int, str, str]]:
    findings = []
    for header_line, header_cells, _rows in find_tables(lines):
        folded = [fold_header(c) for c in header_cells]
        if has_roster_header(folded):
            findings.append(
                (header_line, "roster-table", "Roster table in markdown detected")
            )
    return findings


def check_export_filename(rel: str) -> list[tuple[int, str, str]]:
    path = Path(rel)
    if path.suffix.lower() == ".md":
        return []
    name = path.name
    if name.endswith(".jsonl") and not rel.startswith(".beads/"):
        return [(1, "export-file", "Transcript or Flag export filename detected")]
    for pattern in EXPORT_FILENAME_GLOBS:
        if fnmatch.fnmatch(name.lower(), pattern):
            return [(1, "export-file", "Transcript or Flag export filename detected")]
    return []


def is_exempt_address(token: str) -> bool:
    try:
        addr = ipaddress.ip_interface(token).ip
    except ValueError:
        return True
    if addr.is_loopback:
        return True
    return any(addr in net for net in DOC_NETWORKS)


def check_private_address(lines: list[str]) -> list[tuple[int, str, str]]:
    findings = []
    for lineno, line in enumerate(lines, start=1):
        for regex in (IPV4_RE, IPV6_RE):
            for match in regex.finditer(line):
                token = match.group(0)
                try:
                    addr = ipaddress.ip_interface(token).ip
                except ValueError:
                    continue
                if is_exempt_address(token):
                    continue
                if addr.is_private or addr.is_link_local:
                    findings.append(
                        (
                            lineno,
                            "private-address",
                            "Private or link-local IP address detected",
                        )
                    )
    return findings


def check_network_config(lines: list[str]) -> list[tuple[int, str, str]]:
    findings = []
    for lineno, line in enumerate(lines, start=1):
        for pattern in NETWORK_CONFIG_PATTERNS:
            if pattern.search(line):
                findings.append(
                    (lineno, "network-config", "Network configuration syntax detected")
                )
                break
    return findings


def check_email(lines: list[str]) -> list[tuple[int, str, str]]:
    findings = []
    for lineno, line in enumerate(lines, start=1):
        for match in EMAIL_RE.finditer(line):
            domain = match.group(1)
            if RESERVED_EMAIL_DOMAINS.search(domain):
                continue
            findings.append(
                (lineno, "email-address", "Non-example email address detected")
            )
    return findings


def check_inline_allow(lines: list[str]) -> list[tuple[int, str, str]]:
    findings = []
    for lineno, line in enumerate(lines, start=1):
        if GITLEAKS_ALLOW in line:
            findings.append(
                (lineno, "inline-allow", "Inline secret-scan allow pragma detected")
            )
    return findings


def check_template_fields(lines: list[str]) -> list[tuple[int, str, str]]:
    findings = []
    for _header_line, header_cells, rows in find_tables(lines):
        folded = [fold_header(c) for c in header_cells]
        target_cols = [i for i, c in enumerate(folded) if c in TEMPLATE_FIELD_HEADERS]
        if not target_cols:
            continue
        for lineno, cells in rows:
            for i in target_cols:
                if i < len(cells) and not is_blank(cells[i]):
                    findings.append(
                        (
                            lineno,
                            "template-name-field",
                            "Filled-in name or signature field detected",
                        )
                    )
    for lineno, line in enumerate(lines, start=1):
        for label in TEMPLATE_LABELS:
            label_re = re.compile(re.escape(label) + r":\s*(\S*)")
            for match in label_re.finditer(line):
                if not is_blank(match.group(1)):
                    findings.append(
                        (
                            lineno,
                            "template-name-field",
                            "Filled-in name or signature field detected",
                        )
                    )
    return findings


def check_template_honorific(lines: list[str]) -> list[tuple[int, str, str]]:
    findings = []
    for lineno, line in enumerate(lines, start=1):
        if HONORIFIC_RE.search(line):
            findings.append(
                (lineno, "template-honorific", "Honorific and surname detected")
            )
    return findings


def scan_file(root: Path, rel: str) -> list[tuple[str, int, str, str]]:
    if rel.startswith(".beads/"):
        return []
    path = root / rel
    suffix = path.suffix.lower()
    findings: list[tuple[int, str, str]] = []

    if suffix in SPREADSHEET_EXTENSIONS:
        findings.append((1, "roster-spreadsheet", "Roster spreadsheet file detected"))

    findings.extend(check_export_filename(rel))

    if suffix in BINARY_EXTENSIONS:
        return [(rel, ln, rule, msg) for ln, rule, msg in findings]

    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return [(rel, ln, rule, msg) for ln, rule, msg in findings]

    lines = text.splitlines()

    if suffix in (".csv", ".tsv"):
        findings.extend(check_roster_csv(path, rel, text))

    if suffix == ".md":
        findings.extend(check_roster_table(rel, lines))
        if rel.startswith("docs/templates/"):
            findings.extend(check_template_fields(lines))
            findings.extend(check_template_honorific(lines))

    findings.extend(check_private_address(lines))
    findings.extend(check_network_config(lines))
    findings.extend(check_email(lines))
    findings.extend(check_inline_allow(lines))

    return [(rel, ln, rule, msg) for ln, rule, msg in findings]


def list_files(root: Path) -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "-co", "--exclude-standard", "-z"],
        check=True,
        capture_output=True,
    ).stdout
    return [p for p in out.decode("utf-8", errors="replace").split("\0") if p]


def load_waivers(root: Path) -> tuple[list[dict], list[tuple[str, int, str, str]]]:
    waivers_path = root / "scripts" / "confidentiality-waivers.toml"
    valid: list[dict] = []
    invalid: list[tuple[str, int, str, str]] = []
    rel = "scripts/confidentiality-waivers.toml"
    if not waivers_path.exists():
        return valid, invalid
    data = tomllib.loads(waivers_path.read_text(encoding="utf-8"))
    for entry in data.get("waiver", []):
        missing = REQUIRED_WAIVER_KEYS - entry.keys()
        bad_path = "*" in str(entry.get("path", ""))
        if missing or bad_path:
            reason = f"missing keys: {sorted(missing)}" if missing else "glob in path"
            invalid.append(
                (rel, 1, "waiver-invalid", f"Invalid waiver entry: {reason}")
            )
            continue
        valid.append(entry)
    return valid, invalid


def apply_waivers(
    root: Path, findings: list[tuple[str, int, str, str]], waivers: list[dict]
) -> tuple[list[tuple[str, int, str, str]], list[str]]:
    remaining = []
    waived_lines = []
    active = set()
    for waiver in waivers:
        target = root / waiver["path"]
        if not target.exists():
            continue
        digest = hashlib.sha256(target.read_bytes()).hexdigest()
        if digest == waiver["sha256"]:
            active.add((waiver["path"], waiver["rule"]))
            waived_lines.append(
                f"waived: {waiver['path']} {waiver['rule']} {waiver['bead']}"
            )
    for rel, lineno, rule, msg in findings:
        if (rel, rule) in active:
            continue
        remaining.append((rel, lineno, rule, msg))
    return remaining, waived_lines


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--root", default=".")
    args = parser.parse_args()
    root = Path(args.root).resolve()

    all_findings: list[tuple[str, int, str, str]] = []
    for rel in list_files(root):
        all_findings.extend(scan_file(root, rel))

    waivers, invalid_waivers = load_waivers(root)
    all_findings.extend(invalid_waivers)

    remaining, waived_lines = apply_waivers(root, all_findings, waivers)

    for line in waived_lines:
        print(line)

    remaining.sort(key=lambda f: (f[0], f[1]))
    for rel, lineno, rule, msg in remaining:
        print(f"{rel}:{lineno}: {rule}: {msg}")

    return 1 if remaining else 0


if __name__ == "__main__":
    sys.exit(main())
