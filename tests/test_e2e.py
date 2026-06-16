"""tests/test_e2e.py — e2eアンカー（§10）を conftest 凍結値と照合（AC-20）.

read_minutes → build_prep → build_envelope の通し。封筒契約＋§10アンカー＋決定論。
数値はハードコードせず conftest fixture を使う。
"""

from __future__ import annotations

import pytest

from src.minutes_reader import read_minutes
from src.wbs_reader import read_wbs
from src.prep import build_prep
from src import envelope as envmod


@pytest.fixture
def pipeline(minutes_sample_path, wbs_sample_path):
    reg = read_minutes(str(minutes_sample_path))
    wv = read_wbs(str(wbs_sample_path))
    r_nowbs = build_prep(reg)
    r_wbs = build_prep(reg, wbs_view=wv)
    env = envmod.build_envelope(r_wbs, title="t", project_name="P")
    return r_nowbs, r_wbs, env


class TestE2EAnchors:
    def test_as_of_and_week(self, pipeline, sample_as_of, sample_asof_week):
        _, _, env = pipeline
        assert env["meta"]["as_of"] == sample_as_of
        assert env["meta"]["as_of_week"] == sample_asof_week

    def test_item_count_no_wbs(self, pipeline, sample_item_count_no_wbs):
        r_nowbs, _, _ = pipeline
        assert r_nowbs.summary["item_count"] == sample_item_count_no_wbs

    def test_item_count_with_wbs(self, pipeline, sample_item_count_with_wbs):
        _, _, env = pipeline
        assert env["meta"]["item_count"] == sample_item_count_with_wbs

    def test_upcoming(self, pipeline, sample_upcoming_task):
        _, r_wbs, _ = pipeline
        assert r_wbs.summary["by_kind"]["upcoming_task"] == sample_upcoming_task

    def test_carryover_breakdown(
        self, pipeline, sample_carryover_overdue, sample_carryover_due_soon
    ):
        _, _, env = pipeline
        assert env["meta"]["overdue_count"] == sample_carryover_overdue
        assert env["meta"]["due_soon_count"] >= sample_carryover_due_soon

    def test_decision(self, pipeline, sample_decision_followup):
        _, r_wbs, _ = pipeline
        assert r_wbs.summary["by_kind"]["decision_followup"] == sample_decision_followup

    def test_s1_diff_is_upcoming(self, pipeline, sample_upcoming_task):
        r_nowbs, r_wbs, _ = pipeline
        diff = r_wbs.summary["item_count"] - r_nowbs.summary["item_count"]
        assert diff == sample_upcoming_task


class TestE2EContract:
    def test_envelope_keys_and_ids(self, pipeline):
        _, _, env = pipeline
        assert set(env.keys()) == {
            "schema_version", "skill_id", "ui_type", "ui_type_label", "title",
            "generated_at", "status", "notice", "meta", "payload",
        }
        assert env["skill_id"] == "meeting-prep-skill"
        assert env["ui_type"] == "prep_checklist"

    def test_all_items_have_cellref_ref(self, pipeline):
        _, _, env = pipeline
        for it in env["payload"]["checklist"]:
            assert it["evidence"]
            for ev in it["evidence"]:
                assert "!" in ev["ref"]

    def test_deterministic_except_generated_at(self, minutes_sample_path, wbs_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        wv = read_wbs(str(wbs_sample_path))
        e1 = envmod.build_envelope(build_prep(reg, wbs_view=wv), title="t", project_name="P")
        e2 = envmod.build_envelope(build_prep(reg, wbs_view=wv), title="t", project_name="P")
        e1.pop("generated_at")
        e2.pop("generated_at")
        assert e1 == e2
