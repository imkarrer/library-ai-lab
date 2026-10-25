import hashlib
import shutil
import subprocess
import sys
import time
from pathlib import Path

import confidentiality

REPO_ROOT = Path(__file__).resolve().parent.parent


def _init_repo(root: Path) -> None:
    subprocess.run(["git", "init", "-q"], cwd=root, check=True)


def _run(monkeypatch, capsys, root: Path) -> tuple[int, str]:
    monkeypatch.setattr(sys, "argv", ["confidentiality.py", "--root", str(root)])
    code = confidentiality.main()
    return code, capsys.readouterr().out


def test_roster_csv_header(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "class.csv").write_text("Student Name,Card number\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "roster-csv" in out


def test_roster_tsv_header(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "period3.tsv").write_text("last name\tfirst name\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "roster-csv" in out


def test_roster_spreadsheet_extension(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "roster.xlsx").write_bytes(b"\x00not a real workbook")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "roster-spreadsheet" in out


def test_roster_markdown_table(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "class.md").write_text("| Card | Student |\n|---|---|\n| 14 | Pat |\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "roster-table" in out


def test_transcript_export_filename(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "transcript-2026-10-24.txt").write_text("hello\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "export-file" in out


def test_flags_export_filename(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "flags.jsonl").write_text("{}\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "export-file" in out


def test_private_and_link_local_addresses(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    ipv4 = "10." + "20.30.40"
    cidr = "192.168." + "1.0/24"
    ipv6 = "fd12" + ":3456::1"
    (tmp_path / "notes.md").write_text(f"{ipv4}, {cidr}, {ipv6}\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "private-address" in out


def test_switch_config_syntax(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    line = "switchport" + " access vlan " + "40"
    (tmp_path / "switch.txt").write_text(line + "\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "network-config" in out


def test_firewall_config_syntax(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    ip = "10.0.0." + "5"
    line = "iptables -A" + " INPUT -s " + ip + " -j DROP"
    (tmp_path / "fw.sh").write_text(line + "\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "network-config" in out


def test_template_prepared_by_filled_in(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "docs" / "templates").mkdir(parents=True)
    (tmp_path / "docs" / "templates" / "x.md").write_text("Prepared by: Jane Doe\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "template-name-field" in out


def test_template_name_column_filled_in(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "docs" / "templates").mkdir(parents=True)
    (tmp_path / "docs" / "templates" / "sign.md").write_text(
        "| Name | Role |\n|---|---|\n| Pat Smith | Counselor |\n"
    )
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "template-name-field" in out


def test_template_honorific(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "docs" / "templates").mkdir(parents=True)
    (tmp_path / "docs" / "templates" / "note.md").write_text("Ms. Alvarez will sign.\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "template-honorific" in out


def test_non_example_email(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    email = "jdoe" + "@district.k12.wi.us"
    (tmp_path / "notes.md").write_text(f"contact {email}\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "email-address" in out


def test_inline_allow_pragma(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    pragma = "gitleaks" + ":allow"
    (tmp_path / "leak.env").write_text(f"KEY=abc123  # {pragma}\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "inline-allow" in out


def test_negative_cases_pass(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    templates_dst = tmp_path / "docs" / "templates"
    shutil.copytree(REPO_ROOT / "docs" / "templates", templates_dst)
    (tmp_path / "notes.md").write_text(
        "127.0.0.1, 192.0.2.10 and 2001:db8::1 are examples.\n"
        "Prose about a firewall rule and the VLAN layout is fine.\n"
    )
    (tmp_path / "catalog.csv").write_text("title,author,isbn\n")
    (tmp_path / "ok.md").write_text("reach us at someone@example.org\n")
    beads_dir = tmp_path / ".beads"
    beads_dir.mkdir()
    beads_email = "nobody" + "@district.k12.wi.us"
    (beads_dir / "issues.jsonl").write_text(f'{{"email": "{beads_email}"}}\n')
    gitignore = tmp_path / ".gitignore"
    gitignore.write_text("roster.csv\n")
    (tmp_path / "roster.csv").write_text("Student,Card\n")

    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 0, out
    assert out == ""


def test_force_added_gitignored_roster_reported(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / ".gitignore").write_text("roster.csv\n")
    (tmp_path / "roster.csv").write_text("Student,Card\n")
    subprocess.run(["git", "add", "-f", "roster.csv"], cwd=tmp_path, check=True)
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "roster-csv" in out


def _write_waiver(
    root: Path, waived_path: str, rule: str, digest: str, bead: str
) -> None:
    (root / "scripts").mkdir(parents=True, exist_ok=True)
    (root / "scripts" / "confidentiality-waivers.toml").write_text(
        f"""
[[waiver]]
path = "{waived_path}"
rule = "{rule}"
sha256 = "{digest}"
bead = "{bead}"
reason = "test fixture"
"""
    )


def test_waiver_suppresses_and_prints(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    target = tmp_path / "class.csv"
    target.write_text("Student Name,Card number\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    _write_waiver(tmp_path, "class.csv", "roster-csv", digest, "lib-test")

    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 0, out
    assert "waived: class.csv roster-csv lib-test" in out


def test_waiver_invalidated_by_file_edit(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    target = tmp_path / "class.csv"
    target.write_text("Student Name,Card number\n")
    digest = hashlib.sha256(target.read_bytes()).hexdigest()
    _write_waiver(tmp_path, "class.csv", "roster-csv", digest, "lib-test")

    target.write_text("Student Name,Card number,Extra\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "roster-csv" in out
    assert "waived:" not in out


def test_waiver_missing_bead_is_invalid(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "confidentiality-waivers.toml").write_text(
        """
[[waiver]]
path = "class.csv"
rule = "roster-csv"
sha256 = "deadbeef"
reason = "no bead field"
"""
    )
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "waiver-invalid" in out


def test_waiver_glob_path_is_invalid(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    (tmp_path / "scripts").mkdir(parents=True)
    (tmp_path / "scripts" / "confidentiality-waivers.toml").write_text(
        """
[[waiver]]
path = "docs/*"
rule = "roster-csv"
sha256 = "deadbeef"
bead = "lib-test"
reason = "glob path"
"""
    )
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "waiver-invalid" in out


def test_planted_roster_turns_the_gate_red_then_clean(tmp_path, monkeypatch, capsys):
    _init_repo(tmp_path)
    for rel in subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "-co", "--exclude-standard"],
        check=True,
        capture_output=True,
        text=True,
    ).stdout.splitlines():
        src = REPO_ROOT / rel
        if not src.is_file():
            continue
        dst = tmp_path / rel
        dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(src, dst)
    subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)

    roster = tmp_path / "roster.csv"
    roster.write_text("Student,Card\n")
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 1
    assert "roster-csv" in out

    roster.unlink()
    code, out = _run(monkeypatch, capsys, tmp_path)
    assert code == 0, out


def test_runs_fast_on_this_repo(monkeypatch, capsys):
    start = time.monotonic()
    code, _out = _run(monkeypatch, capsys, REPO_ROOT)
    assert time.monotonic() - start < 2
    assert code == 0
