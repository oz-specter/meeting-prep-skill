"""G1 段: src/model.py の単体テスト ＋ conftest 健全性（e2eアンカー凍結）.

確認項目:
- CellRef.render() の書式（note なし / note あり）・`!` を含む
- CellRef が frozen（代入で FrozenInstanceError）
- MissingColumnReport の生成とフィールド確認
- Risk を import できないこと（specs §11「Risk は持たない」の担保）
- conftest 健全性（議事録/WBS path が実在パスを返す）
- conftest アンカー定数 fixture が specs §10 の凍結値どおり

由来: D1 report-skill/tests/test_model.py。アンカーは D3 規約（as_of=議事録最新会議日）に差し替え。
"""

from __future__ import annotations

import dataclasses
import importlib

import pytest

from src.model import CellRef, MissingColumnReport


# ---------------------------------------------------------------------------
# CellRef.render() 書式テスト
# ---------------------------------------------------------------------------

class TestCellRefRender:
    def test_render_no_note(self):
        ref = CellRef("議事録", "C", 5, "Fit-Gap方針を承認")
        assert ref.render() == '議事録!C5 = "Fit-Gap方針を承認"'

    def test_render_contains_exclamation(self):
        ref = CellRef("議事録", "C", 5, "決定")
        assert "!" in ref.render()

    def test_render_with_note(self):
        ref = CellRef("議事録", "F", 10, "CN-02", "宿題_担当")
        result = ref.render()
        assert result.endswith(" → 宿題_担当")
        assert "!" in result

    def test_render_note_format(self):
        ref = CellRef("WBS", "E", 3, "2026-07-15", "開始日")
        assert " → 開始日" in ref.render()


# ---------------------------------------------------------------------------
# CellRef frozen テスト
# ---------------------------------------------------------------------------

class TestCellRefFrozen:
    def test_frozen_sheet(self):
        ref = CellRef("議事録", "C", 5, "決定")
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError)):
            ref.sheet = "別シート"  # type: ignore[misc]

    def test_frozen_value(self):
        ref = CellRef("議事録", "C", 5, "決定")
        with pytest.raises((dataclasses.FrozenInstanceError, TypeError)):
            ref.value = "別決定"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# MissingColumnReport テスト
# ---------------------------------------------------------------------------

class TestMissingColumnReport:
    def test_create_basic(self):
        report = MissingColumnReport("議事録", ["決定事項"], "x")
        assert report.sheet == "議事録"
        assert report.missing_columns == ["決定事項"]
        assert report.suggestion == "x"

    def test_create_multiple_missing(self):
        report = MissingColumnReport("議事録", ["日付", "決定事項"])
        assert len(report.missing_columns) == 2

    def test_suggestion_default_empty(self):
        report = MissingColumnReport("議事録", ["会議体"])
        assert report.suggestion == ""


# ---------------------------------------------------------------------------
# Risk を import できないこと（specs §11「Risk は持たない」の担保）
# ---------------------------------------------------------------------------

class TestNoRisk:
    def test_risk_import_error(self):
        with pytest.raises((ImportError, AttributeError)):
            mod = importlib.import_module("src.model")
            _ = mod.Risk  # type: ignore[attr-defined]


# ---------------------------------------------------------------------------
# conftest 健全性テスト（サンプル実在・e2eアンカー凍結値確認・specs §10）
# ---------------------------------------------------------------------------

class TestConftestSanity:
    def test_minutes_sample_exists(self, minutes_sample_path):
        assert minutes_sample_path.exists(), f"ファイルが存在しない: {minutes_sample_path}"

    def test_wbs_sample_exists(self, wbs_sample_path):
        assert wbs_sample_path.exists(), f"ファイルが存在しない: {wbs_sample_path}"

    def test_anchor_meeting_count(self, sample_meeting_count):
        assert sample_meeting_count == 6

    def test_anchor_as_of(self, sample_as_of):
        assert sample_as_of == "2026-07-10"

    def test_anchor_asof_week(self, sample_asof_week):
        assert sample_asof_week == "2026-W28"

    def test_anchor_horizon_days(self, sample_horizon_days):
        assert sample_horizon_days == 14

    def test_anchor_carryover_overdue(self, sample_carryover_overdue):
        assert sample_carryover_overdue == 5

    def test_anchor_carryover_due_soon(self, sample_carryover_due_soon):
        assert sample_carryover_due_soon == 1

    def test_anchor_carryover_pending(self, sample_carryover_pending):
        assert sample_carryover_pending == 0

    def test_anchor_carryover_total(self, sample_carryover_total):
        assert sample_carryover_total == 6

    def test_anchor_decision_followup(self, sample_decision_followup):
        assert sample_decision_followup == 5

    def test_anchor_wbs_task_count(self, sample_wbs_task_count):
        assert sample_wbs_task_count == 81

    def test_anchor_upcoming_task(self, sample_upcoming_task):
        assert sample_upcoming_task == 13

    def test_anchor_item_count_no_wbs(self, sample_item_count_no_wbs):
        assert sample_item_count_no_wbs == 11

    def test_anchor_item_count_with_wbs(self, sample_item_count_with_wbs):
        assert sample_item_count_with_wbs == 24

    def test_anchor_item_count_consistency(
        self, sample_item_count_no_wbs, sample_upcoming_task, sample_item_count_with_wbs
    ):
        """S-1: WBS有 item_count = WBS無 + upcoming_task（差分の整合）."""
        assert sample_item_count_no_wbs + sample_upcoming_task == sample_item_count_with_wbs

    def test_anchor_carryover_breakdown_consistency(
        self,
        sample_carryover_overdue,
        sample_carryover_due_soon,
        sample_carryover_pending,
        sample_carryover_total,
    ):
        """carryover 内訳の合計が total と一致."""
        assert (
            sample_carryover_overdue
            + sample_carryover_due_soon
            + sample_carryover_pending
            == sample_carryover_total
        )
