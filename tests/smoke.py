"""Live smoke test against jira.hh.ru. Run manually after substantial changes.

Usage: ~/.local/pipx/venvs/bjira/bin/python tests/smoke.py
"""
import json
import subprocess
from pathlib import Path

import keyring
from jira import JIRA

CONFIG = json.loads((Path.home() / ".bjira_config").read_text())
USER = CONFIG["user"]
HOST = CONFIG["host"]
ISSUE = "PORTFOLIO-53307"

jira = JIRA(server=HOST, basic_auth=(USER, keyring.get_password("bjira", USER)))


def run(cmd):
    print(f"$ {' '.join(cmd)}")
    r = subprocess.run(cmd, capture_output=True, text=True)
    print(r.stdout)
    if r.returncode != 0:
        print(f"  stderr: {r.stderr}")
    return r


def main():
    print("=== 1. comments (read) ===")
    r = run(["bjira", "comments", ISSUE, "-n", "1"])
    assert r.returncode == 0, "comments read failed"

    print("\n=== 2. comment add → delete ===")
    r = run(["bjira", "comment", ISSUE, "[SMOKE] test — auto-delete"])
    assert r.returncode == 0, "comment add failed"
    cid = r.stdout.split("id=")[1].split()[0]
    jira.comment(ISSUE, cid).delete()
    print(f"  deleted comment {cid}")

    print("\n=== 3. edit --summary <same> (no-op) ===")
    current = jira.issue(ISSUE, fields="summary").fields.summary
    r = run(["bjira", "edit", ISSUE, "--summary", current])
    assert r.returncode == 0, "no-op summary failed"
    assert "no changes" in r.stdout, f"expected 'no changes' in output, got: {r.stdout!r}"

    print("\n=== 4. status — unknown transition check ===")
    r = run(["bjira", "status", ISSUE, "nonexistent"])
    assert r.returncode == 3, f"expected exit 3, got {r.returncode}"
    print("  correctly returned exit 3 for unknown transition")

    print("\n=== 5. link — unknown type check ===")
    r = run(["bjira", "link", ISSUE, "NotARealType", ISSUE])
    assert r.returncode == 3, f"expected exit 3, got {r.returncode}"
    print("  correctly returned exit 3 for unknown link type")

    print("\n=== all smoke checks passed ===")


if __name__ == "__main__":
    main()
