"""tests/test_envelope.py — build_envelope / from_missing_report（AC-11/13/14）.

封筒トップレベル10キー（A1互換）・skill_id/ui_type・meta加算キー・evidence6キー・
notice契約・degraded。数値はサンプル fixture 参照。
"""

from __future__ import annotations

import datetime
import json

import pytest

from src.minutes_reader import read_minutes
from src.model import MissingColumnReport
from src.wbs_reader import read_wbs
from src.prep import build_prep
from src import envelope as envmod


_TOP_KEYS = {
    "schema_version", "skill_id", "ui_type", "ui_type_label", "title",
    "generated_at", "status", "notice", "meta", "payload",
}
_META_KEYS = {
    "project_name", "project_type", "item_count", "overdue_count",
    "due_soon_count", "as_of", "as_of_week", "unit",
}


@pytest.fixture
def env_wbs(minutes_sample_path, wbs_sample_path):
    reg = read_minutes(str(minutes_sample_path))
    wv = read_wbs(str(wbs_sample_path))
    r = build_prep(reg, wbs_view=wv)
    return envmod.build_envelope(r, title="t", project_name="P")


class TestEnvelopeContract:
    def test_top_level_10_keys(self, env_wbs):
        assert set(env_wbs.keys()) == _TOP_KEYS

    def test_skill_and_ui_type(self, env_wbs):
        assert env_wbs["skill_id"] == "meeting-prep-skill"
        assert env_wbs["ui_type"] == "prep_checklist"
        assert env_wbs["ui_type_label"]

    def test_meta_keys_and_unit(self, env_wbs):
        assert set(env_wbs["meta"].keys()) == _META_KEYS
        assert env_wbs["meta"]["unit"] == "件"
        assert env_wbs["meta"]["project_type"] is None

    def test_meta_counts_match_sample(
        self, env_wbs, sample_item_count_with_wbs, sample_carryover_overdue
    ):
        m = env_wbs["meta"]
        assert m["item_count"] == sample_item_count_with_wbs
        assert m["overdue_count"] == sample_carryover_overdue
        assert m["as_of"] == "2026-07-10"

    def test_generated_at_is_seconds_iso(self, env_wbs):
        datetime.datetime.fromisoformat(env_wbs["generated_at"])

    def test_payload_no_time_keys(self, env_wbs):
        assert "generated_at" not in env_wbs["payload"]
        assert "generated_at" not in env_wbs["meta"]

    def test_payload_shape(self, env_wbs):
        pl = env_wbs["payload"]
        for k in ("as_of", "as_of_week", "horizon_days", "meeting_scope",
                  "headline", "checklist", "summary", "overdue_note", "recommended_actions"):
            assert k in pl

    def test_evidence_six_keys_and_ref(self, env_wbs):
        for it in env_wbs["payload"]["checklist"]:
            for ev in it["evidence"]:
                assert set(ev.keys()) == {"sheet", "column", "row", "value", "note", "ref"}
                assert "!" in ev["ref"]

    def test_dumps_roundtrip(self, env_wbs):
        s = envmod.dumps(env_wbs)
        assert json.loads(s) == env_wbs
        assert "\\u" not in s


class TestNoticeContract:
    def test_notice_none_when_clean(self, env_wbs):
        assert env_wbs["notice"] is None

    def test_notice_passthrough_on_freshness(self, minutes_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        r = build_prep(reg, as_of="2026-09-01")
        env = envmod.build_envelope(r, title="t", project_name="P")
        assert env["notice"] is not None
        assert env["notice"].get("stale_minutes") == 53


class TestDegraded:
    def _report(self):
        return MissingColumnReport(sheet="議事録", missing_columns=["決定事項"], suggestion="s")

    def test_status_degraded(self):
        env = envmod.from_missing_report(self._report(), project_name="P")
        assert env["status"] == "degraded"
        assert set(env.keys()) == _TOP_KEYS

    def test_notice_schema(self):
        env = envmod.from_missing_report(self._report(), project_name="P")
        assert set(env["notice"].keys()) == {"sheet", "missing_columns", "suggestion"}

    def test_empty_payload_and_meta_zeros(self):
        env = envmod.from_missing_report(self._report(), project_name="P")
        assert env["payload"]["checklist"] == []
        assert env["payload"]["summary"]["item_count"] == 0
        assert env["meta"]["item_count"] == 0
        assert env["meta"]["as_of"] is None
        assert env["meta"]["unit"] == "件"
