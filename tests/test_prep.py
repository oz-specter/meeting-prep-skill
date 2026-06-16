"""tests/test_prep.py — build_prep（G5: 議事録だけで動く核）の受け入れテスト.

対象 AC: AC-3（carryover全件）・AC-4/S-2（status 閉区間）・AC-5（decision_followup）・
AC-8/S-5（並び・安定）・AC-12（headline/recommended_actions）・AC-18（deepcopy冪等）・
AC-10 一部（evidence は CellRef・ref==render()）。
アンカー（§10）: A-1 as_of / A-2 as_of_week / A-4 carryover内訳 / A-5 decision / A-8 item_count。
**数値はハードコードせず conftest fixture を使う**（確定リファレンス運用）。

合成テスト用の register は MeetingEntry/SheetView を直接組む（サンプル正本へ書き込まない）。
"""

from __future__ import annotations

import copy
import datetime

import pytest

from src.config import (
    HEADLINE_FORMAT_EMPTY,
    OVERDUE_NOTE,
    STATUS_ORDER,
)
from src.minutes_reader import MeetingEntry, MinutesRegister, SheetView, read_minutes
from src.model import CellRef
from src.prep import ChecklistItem, PrepResult, build_prep


# ---------------------------------------------------------------------------
# 合成 register ファクトリ（サンプル非依存の境界テスト用）
# ---------------------------------------------------------------------------

_COL_LETTER = {
    "日付": "A", "会議体": "B", "決定事項": "C", "出席": "D",
    "宿題_内容": "E", "宿題_担当": "F", "宿題_期限": "G",
    "関連タスク": "H", "関連要件": "I",
}


def _entry(
    row: int,
    date: str,
    *,
    mtype: str = "定例",
    decision: str = "",
    homework: str = "",
    owner: str = "",
    deadline: "str | None" = None,
    related_tasks: "list | None" = None,
) -> MeetingEntry:
    d = datetime.date.fromisoformat(date)
    dl = datetime.date.fromisoformat(deadline) if deadline else None
    return MeetingEntry(
        meeting_date=d,
        date_raw=date,
        date_str=d.isoformat(),
        meeting_type=mtype,
        decision=decision,
        attendees=[],
        homework_content=homework,
        homework_owner=owner,
        deadline=dl,
        deadline_raw=deadline or "",
        deadline_str=(dl.isoformat() if dl else ""),
        deadline_unparseable=False,
        related_tasks=related_tasks or [],
        related_reqs=[],
        excel_row=row,
    )


def _register(entries: list) -> MinutesRegister:
    view = SheetView(sheet="議事録", header_row=1, col_letter=dict(_COL_LETTER))
    return MinutesRegister(entries=entries, view=view)


# ---------------------------------------------------------------------------
# サンプル fixture（実物の議事録 → PrepResult）
# ---------------------------------------------------------------------------

@pytest.fixture
def prep_sample(minutes_sample_path) -> PrepResult:
    """サンプル議事録から既定 as_of（最新会議日）で build_prep した結果."""
    reg = read_minutes(str(minutes_sample_path))
    assert isinstance(reg, MinutesRegister), "サンプル議事録は読めるはず"
    return build_prep(reg)


# ===========================================================================
# as_of 規約（A-1 / A-2 / 既定 horizon）
# ===========================================================================

class TestAsOf:
    def test_default_as_of_is_latest_meeting(self, prep_sample, sample_as_of):
        assert prep_sample.as_of == sample_as_of

    def test_as_of_week(self, prep_sample, sample_asof_week):
        assert prep_sample.as_of_week == sample_asof_week

    def test_default_horizon(self, prep_sample, sample_horizon_days):
        assert prep_sample.horizon_days == sample_horizon_days

    def test_explicit_as_of_overrides(self):
        reg = _register([_entry(2, "2026-01-01", homework="x", deadline="2026-01-01")])
        res = build_prep(reg, as_of="2026-03-01")
        assert res.as_of == "2026-03-01"

    def test_raises_when_no_as_of(self):
        # 会議日が1件も無い（entries 空）→ as_of 決定不能。
        with pytest.raises(ValueError):
            build_prep(_register([]))


# ===========================================================================
# AC-3: carryover_action は宿題非空の全件
# ===========================================================================

class TestCarryover:
    def test_total_count(self, prep_sample, sample_carryover_total):
        carry = [i for i in prep_sample.checklist if i.kind == "carryover_action"]
        assert len(carry) == sample_carryover_total

    def test_status_breakdown(
        self,
        prep_sample,
        sample_carryover_overdue,
        sample_carryover_due_soon,
        sample_carryover_pending,
    ):
        carry = [i for i in prep_sample.checklist if i.kind == "carryover_action"]
        by = {"overdue": 0, "due_soon": 0, "pending": 0}
        for i in carry:
            by[i.status] += 1
        assert by["overdue"] == sample_carryover_overdue
        assert by["due_soon"] == sample_carryover_due_soon
        assert by["pending"] == sample_carryover_pending

    def test_completion_not_inferred(self, prep_sample):
        # 完了状態は推測しない＝overdue_note を必ず保持（★#4・§8-2）。
        assert prep_sample.overdue_note == OVERDUE_NOTE

    def test_empty_homework_excluded(self):
        reg = _register([
            _entry(2, "2026-05-01", homework=""),       # 宿題なし → 不採用
            _entry(3, "2026-05-02", homework="資料作成", deadline="2026-05-10"),
        ])
        res = build_prep(reg, as_of="2026-05-02")
        carry = [i for i in res.checklist if i.kind == "carryover_action"]
        assert len(carry) == 1
        assert carry[0].title == "資料作成"


# ===========================================================================
# AC-4 / S-2: status 分岐（§3.2・閉区間）
# ===========================================================================

class TestStatusBoundary:
    def _status(self, deadline, *, as_of="2026-06-01", horizon=14):
        reg = _register([_entry(2, "2026-06-01", homework="hw", deadline=deadline)])
        res = build_prep(reg, as_of=as_of, horizon_days=horizon)
        carry = [i for i in res.checklist if i.kind == "carryover_action"]
        return carry[0].status

    def test_deadline_equals_as_of_is_overdue(self):
        assert self._status("2026-06-01") == "overdue"

    def test_deadline_before_as_of_is_overdue(self):
        assert self._status("2026-05-20") == "overdue"

    def test_deadline_inside_window_is_due_soon(self):
        assert self._status("2026-06-08") == "due_soon"

    def test_deadline_equals_window_upper_is_due_soon(self):
        # as_of + horizon = 2026-06-15（閉区間・上端含む）。
        assert self._status("2026-06-15") == "due_soon"

    def test_deadline_after_window_is_pending(self):
        assert self._status("2026-06-16") == "pending"

    def test_no_deadline_is_pending(self):
        assert self._status(None) == "pending"


# ===========================================================================
# AC-5: decision_followup（RK-/R- 参照を含む決定のみ・status=pending）
# ===========================================================================

class TestDecisionFollowup:
    def test_count(self, prep_sample, sample_decision_followup):
        dec = [i for i in prep_sample.checklist if i.kind == "decision_followup"]
        assert len(dec) == sample_decision_followup

    def test_all_pending(self, prep_sample):
        dec = [i for i in prep_sample.checklist if i.kind == "decision_followup"]
        assert dec, "decision_followup が1件以上あるはず"
        assert all(i.status == "pending" for i in dec)
        assert all(i.due == "" for i in dec)

    def test_only_ref_decisions(self):
        reg = _register([
            _entry(2, "2026-05-01", decision="Fit-Gap方針を承認（RK-05対応）"),
            _entry(3, "2026-05-02", decision="次回までに見積を提示"),   # 参照なし → 不採用
            _entry(4, "2026-05-03", decision="R-12 のリスク受容を決定"),
        ])
        res = build_prep(reg, as_of="2026-05-03")
        dec = [i for i in res.checklist if i.kind == "decision_followup"]
        assert len(dec) == 2
        titles = {i.title for i in dec}
        assert "次回までに見積を提示" not in titles


# ===========================================================================
# AC-8 / S-5: 並び（status→期日→出現順・安定・入力順非依存）
# ===========================================================================

class TestSorting:
    def test_status_then_due_monotonic(self, prep_sample):
        # checklist は (STATUS_ORDER, 期日) で単調非減少。
        prev = None
        for it in prep_sample.checklist:
            due_key = (0, it._due_date.toordinal()) if it._due_date else (1, 0)
            key = (STATUS_ORDER[it.status], due_key)
            if prev is not None:
                assert prev <= key
            prev = key

    def test_input_permutation_invariant(self, minutes_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        res_a = build_prep(reg)
        reg2 = read_minutes(str(minutes_sample_path))
        reg2.entries.reverse()                       # 入力行を入れ替え
        res_b = build_prep(reg2)
        key_a = [(i.kind, i.status, i.title, i.due, i.excel_row) for i in res_a.checklist]
        key_b = [(i.kind, i.status, i.title, i.due, i.excel_row) for i in res_b.checklist]
        assert key_a == key_b


# ===========================================================================
# AC-12: headline / summary / recommended_actions（決定論固定順）
# ===========================================================================

class TestHeadlineSummary:
    def test_item_count_no_wbs(self, prep_sample, sample_item_count_no_wbs):
        assert prep_sample.summary["item_count"] == sample_item_count_no_wbs

    def test_by_status_sums_to_item_count(self, prep_sample):
        s = prep_sample.summary
        assert sum(s["by_status"].values()) == s["item_count"]

    def test_by_kind_sums_to_item_count(self, prep_sample):
        s = prep_sample.summary
        assert sum(s["by_kind"].values()) == s["item_count"]

    def test_headline_mentions_counts(self, prep_sample):
        # 自由文生成なし＝config 書式に件数が埋まっている。
        s = prep_sample.summary
        assert str(s["item_count"]) in prep_sample.headline

    def test_recommended_actions_order(
        self, prep_sample, sample_carryover_overdue, sample_decision_followup
    ):
        # G5: overdue>0・decision>0・upcoming=0・freshness=0 →（overdue, decision）の固定順。
        ra = prep_sample.recommended_actions
        assert len(ra) == 2
        assert str(sample_carryover_overdue) in ra[0]      # (1) overdue 文が先頭
        assert str(sample_decision_followup) in ra[1]      # (3) decision 文が後

    def test_empty_recommended_is_list(self):
        reg = _register([_entry(2, "2026-05-01", mtype="定例")])  # 宿題も参照決定もなし
        res = build_prep(reg, as_of="2026-05-01")
        assert res.summary["item_count"] == 0
        assert res.recommended_actions == []
        assert res.headline == HEADLINE_FORMAT_EMPTY


# ===========================================================================
# AC-10（一部）: evidence は CellRef 由来・ref==render()
# ===========================================================================

class TestEvidence:
    def test_every_item_has_cellref_evidence(self, prep_sample):
        for it in prep_sample.checklist:
            assert it.evidence, f"evidence 空: {it.kind}/{it.title}"
            for ev in it.evidence:
                assert isinstance(ev, CellRef)

    def test_carryover_evidence_includes_homework_cell(self):
        reg = _register([
            _entry(2, "2026-05-01", homework="資料作成", owner="山田", deadline="2026-05-10"),
        ])
        res = build_prep(reg, as_of="2026-05-01")
        ev = res.checklist[0].evidence
        cols = {c.column for c in ev}
        assert "E" in cols   # 宿題_内容
        # render() は手組みでなく CellRef 由来。
        assert all(c.render() == c.render() for c in ev)
        assert any('資料作成' in c.render() for c in ev)


# ===========================================================================
# AC-18: deepcopy 冪等・入力非破壊
# ===========================================================================

class TestIdempotent:
    def test_repeated_run_equal(self, minutes_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        r1 = build_prep(reg)
        r2 = build_prep(reg)
        assert r1 == r2

    def test_input_not_mutated(self, minutes_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        before = copy.deepcopy(reg.entries)
        build_prep(reg)
        assert reg.entries == before
