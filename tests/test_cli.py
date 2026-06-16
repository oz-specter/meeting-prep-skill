"""tests/test_cli.py — CLI 実走（AC-15/16/17）.

5format×WBS有無・CSV BOM/9列・exit規約（0/2）・degraded envelope・meeting_scope。
サンプル正本には書き込まない（--out は tmp_path）。
"""

from __future__ import annotations

import csv as _csv
import io
import json
from pathlib import Path

import pytest

from src.cli import main


def _only(out_dir: Path, suffix: str) -> Path:
    files = [p for p in out_dir.glob("*") if p.name.endswith(suffix)]
    assert len(files) == 1, [p.name for p in out_dir.glob("*")]
    return files[0]


class TestFormats:
    @pytest.mark.parametrize("fmt,suffix", [
        ("md", ".md"), ("html", ".html"), ("json", ".json"),
        ("csv", ".csv"), ("envelope", ".envelope.json"),
    ])
    def test_each_format_wbs(self, fmt, suffix, tmp_path, minutes_sample_path, wbs_sample_path):
        out = tmp_path / fmt
        rc = main([
            "--minutes", str(minutes_sample_path),
            "--wbs", str(wbs_sample_path),
            "--out", str(out), "--format", fmt, "--project-name", "P",
        ])
        assert rc == 0
        assert _only(out, suffix).exists()

    def test_md_without_wbs(self, tmp_path, minutes_sample_path):
        out = tmp_path / "nowbs"
        rc = main(["--minutes", str(minutes_sample_path), "--out", str(out), "--format", "md"])
        assert rc == 0
        assert _only(out, ".md").exists()


class TestCsvContract:
    def test_bom_and_9_cols(self, tmp_path, minutes_sample_path, wbs_sample_path):
        out = tmp_path / "csv"
        main(["--minutes", str(minutes_sample_path), "--wbs", str(wbs_sample_path),
              "--out", str(out), "--format", "csv", "--project-name", "P"])
        raw = _only(out, ".csv").read_bytes()
        assert raw[:3] == b"\xef\xbb\xbf"
        rows = list(_csv.reader(io.StringIO(raw.decode("utf-8-sig"))))
        assert all(len(r) == 9 for r in rows)
        assert rows[0][0] == "プロジェクト"


class TestEnvelopeOutput:
    def test_valid_envelope_10_keys(self, tmp_path, minutes_sample_path, wbs_sample_path):
        out = tmp_path / "env"
        main(["--minutes", str(minutes_sample_path), "--wbs", str(wbs_sample_path),
              "--out", str(out), "--format", "envelope", "--project-name", "P"])
        env = json.loads(_only(out, ".envelope.json").read_text(encoding="utf-8"))
        assert env["skill_id"] == "meeting-prep-skill"
        assert env["ui_type"] == "prep_checklist"
        assert len(env.keys()) == 10

    def test_history_written(self, tmp_path, minutes_sample_path):
        out = tmp_path / "h"
        main(["--minutes", str(minutes_sample_path), "--out", str(out), "--format", "md"])
        assert (out / "history.jsonl").exists()


class TestExitCodes:
    def test_missing_file_md_exit2(self, tmp_path, minutes_sample_path):
        out = tmp_path / "m"
        rc = main(["--minutes", str(tmp_path / "nope.xlsx"), "--out", str(out), "--format", "md"])
        assert rc == 2

    def test_missing_file_envelope_degraded_exit0(self, tmp_path):
        out = tmp_path / "d"
        rc = main(["--minutes", str(tmp_path / "nope.xlsx"), "--out", str(out), "--format", "envelope"])
        assert rc == 0
        env = json.loads(_only(out, ".envelope.json").read_text(encoding="utf-8"))
        assert env["status"] == "degraded"


class TestMeetingScope:
    def test_scope_reflected_and_subset(self, tmp_path, minutes_sample_path, wbs_sample_path):
        out_all = tmp_path / "all"
        out_scope = tmp_path / "scope"
        main(["--minutes", str(minutes_sample_path), "--wbs", str(wbs_sample_path),
              "--out", str(out_all), "--format", "json", "--project-name", "P"])
        main(["--minutes", str(minutes_sample_path), "--wbs", str(wbs_sample_path),
              "--out", str(out_scope), "--format", "json", "--project-name", "P",
              "--meeting-type", "週次定例"])
        d_all = json.loads(_only(out_all, ".json").read_text(encoding="utf-8"))
        d_scope = json.loads(_only(out_scope, ".json").read_text(encoding="utf-8"))
        assert d_scope["meeting_scope"] == "週次定例"
        cd_all = {(i["kind"], i["title"]) for i in d_all["checklist"]
                  if i["kind"] in ("carryover_action", "decision_followup")}
        cd_scope = {(i["kind"], i["title"]) for i in d_scope["checklist"]
                    if i["kind"] in ("carryover_action", "decision_followup")}
        assert cd_scope <= cd_all
        up_all = len([i for i in d_all["checklist"] if i["kind"] == "upcoming_task"])
        up_scope = len([i for i in d_scope["checklist"] if i["kind"] == "upcoming_task"])
        assert up_scope == up_all
