"""tests/test_prep.py — build_prep（G5: 議事録の核 ＋ G6: WBS依存）の受け入れテスト.

対象 AC:
  G5: AC-3（carryover全件）・AC-4/S-2（status 閉区間）・AC-5（decision）・AC-8/S-5（並び安定）・
      AC-12（headline/recommended）・AC-18（deepcopy冪等）・AC-10一部（evidence CellRef）。
  G6: AC-6（upcoming_task）・AC-7/S-1（WBS有無で3区分不変・差分=upcoming/related_phases）・
      AC-9（freshness）・AC-17/S-4（meeting_scope）・AC-13（notice契約）・AC-19（unknown_tasks）。
アンカー（§10）: A-1/A-2/A-4/A-5/A-6/A-7/A-8/A-9。
**数値はハードコードせず conftest fixture を使う**（確定リファレンス運用）。

合成テスト用の register/wbs は dataclass を直接組む（サンプル正本へ書き込まない）。
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
from src.wbs_reader import WbsView, read_wbs
from src.prep import ChecklistItem, PrepResult, build_prep


# ---------------------------------------------------------------------------
# 合成 register / wbs ファクトリ（サンプル非依存の境界テスト用）
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


_WBS_COL_LETTER = {
    "タスクID": "A", "タスク名": "B", "担当": "C",
    "開始日": "D", "終了日": "E", "工程": "F",
}


def _wbs(tasks: list) -> WbsView:
    """tasks: list of dict(id,row,name,owner,start,end,phase). 値は date 文字列でも date でも可."""
    rows: dict = {}
    values: dict = {}
    for t in tasks:
        tid = t["id"]
        rows[tid] = t["row"]
        values[(tid, "タスクID")] = tid
        values[(tid, "タスク名")] = t.get("name", tid)
        values[(tid, "担当")] = t.get("owner", "")
        values[(tid, "開始日")] = t.get("start")
        values[(tid, "終了日")] = t.get("end")
        values[(tid, "工程")] = t.get("phase")
    return WbsView(sheet="WBS", col_letter=dict(_WBS_COL_LETTER), rows=rows, _values=values)


# ---------------------------------------------------------------------------
# サンプル fixture（実物 → PrepResult）
# ---------------------------------------------------------------------------

@pytest.fixture
def prep_sample(minutes_sample_path) -> PrepResult:
    """サンプル議事録のみ・既定 as_of（最新会議日）で build_prep。"""
    reg = read_minutes(str(minutes_sample_path))
    assert isinstance(reg, MinutesRegister), "サンプル議事録は読めるはず"
    return build_prep(reg)


@pytest.fixture
def prep_sample_wbs(minutes_sample_path, wbs_sample_path) -> PrepResult:
    """サンプル議事録＋WBS・既定 as_of で build_prep。"""
    reg = read_minutes(str(minutes_sample_path))
    wv = read_wbs(str(wbs_sample_path))
    assert isinstance(reg, MinutesRegister) and wv is not None
    return build_prep(reg, wbs_view=wv)


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
        assert prep_sample.overdue_note == OVERDUE_NOTE

    def test_empty_homework_excluded(self):
        reg = _register([
            _entry(2, "2026-05-01", homework=""),
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
            _entry(3, "2026-05-02", decision="次回までに見積を提示"),
            _entry(4, "2026-05-03", decision="R-12 のリスク受容を決定"),
        ])
        res = build_prep(reg, as_of="2026-05-03")
        dec = [i for i in res.checklist if i.kind == "decision_followup"]
        assert len(dec) == 2
        assert "次回までに見積を提示" not in {i.title for i in dec}


# ===========================================================================
# AC-8 / S-5: 並び（status→期日→出現順・安定・入力順非依存）
# ===========================================================================

class TestSorting:
    def test_status_then_due_monotonic(self, prep_sample_wbs):
        prev = None
        for it in prep_sample_wbs.checklist:
            due_key = (0, it._due_date.toordinal()) if it._due_date else (1, 0)
            key = (STATUS_ORDER[it.status], due_key)
            if prev is not None:
                assert prev <= key
            prev = key

    def test_input_permutation_invariant(self, minutes_sample_path, wbs_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        wv = read_wbs(str(wbs_sample_path))
        res_a = build_prep(reg, wbs_view=wv)
        reg2 = read_minutes(str(minutes_sample_path))
        reg2.entries.reverse()
        res_b = build_prep(reg2, wbs_view=wv)
        key_a = [(i.kind, i.status, i.title, i.due, i.source_rank, i.excel_row)
                 for i in res_a.checklist]
        key_b = [(i.kind, i.status, i.title, i.due, i.source_rank, i.excel_row)
                 for i in res_b.checklist]
        assert key_a == key_b

    def test_full_sort_key_monotonic(self, prep_sample_wbs):
        # フルソートキー (status, 期日, source_rank, excel_row) が単調非減少
        # ＝議事録由来(source_rank=0)が同status・同期日のWBS由来(1)より必ず先（§3.3）。
        prev = None
        for it in prep_sample_wbs.checklist:
            due_key = (0, it._due_date.toordinal()) if it._due_date else (1, 0)
            key = (STATUS_ORDER[it.status], due_key, it.source_rank, it.excel_row)
            if prev is not None:
                assert prev <= key
            prev = key


# ===========================================================================
# AC-12: headline / summary / recommended_actions（決定論固定順）
# ===========================================================================

class TestHeadlineSummary:
    def test_item_count_no_wbs(self, prep_sample, sample_item_count_no_wbs):
        assert prep_sample.summary["item_count"] == sample_item_count_no_wbs

    def test_by_status_sums_to_item_count(self, prep_sample_wbs):
        s = prep_sample_wbs.summary
        assert sum(s["by_status"].values()) == s["item_count"]

    def test_by_kind_sums_to_item_count(self, prep_sample_wbs):
        s = prep_sample_wbs.summary
        assert sum(s["by_kind"].values()) == s["item_count"]

    def test_headline_mentions_counts(self, prep_sample):
        assert str(prep_sample.summary["item_count"]) in prep_sample.headline

    def test_recommended_actions_no_wbs(
        self, prep_sample, sample_carryover_overdue, sample_decision_followup
    ):
        # WBS無: overdue>0・decision>0・upcoming=0・freshness=0 →（overdue, decision）。
        ra = prep_sample.recommended_actions
        assert len(ra) == 2
        assert str(sample_carryover_overdue) in ra[0]
        assert str(sample_decision_followup) in ra[1]

    def test_recommended_actions_wbs_order(
        self, prep_sample_wbs, sample_carryover_overdue,
        sample_upcoming_task, sample_decision_followup
    ):
        # WBS有: (1)overdue (2)upcoming (3)decision の固定順。
        ra = prep_sample_wbs.recommended_actions
        assert len(ra) == 3
        assert str(sample_carryover_overdue) in ra[0]
        assert str(sample_upcoming_task) in ra[1]
        assert str(sample_decision_followup) in ra[2]

    def test_empty_recommended_is_list(self):
        reg = _register([_entry(2, "2026-05-01", mtype="定例")])
        res = build_prep(reg, as_of="2026-05-01")
        assert res.summary["item_count"] == 0
        assert res.recommended_actions == []
        assert res.headline == HEADLINE_FORMAT_EMPTY


# ===========================================================================
# AC-10（一部）: evidence は CellRef 由来・ref==render()
# ===========================================================================

class TestEvidence:
    def test_every_item_has_cellref_evidence(self, prep_sample_wbs):
        for it in prep_sample_wbs.checklist:
            assert it.evidence, f"evidence 空: {it.kind}/{it.title}"
            for ev in it.evidence:
                assert isinstance(ev, CellRef)

    def test_carryover_evidence_includes_homework_cell(self):
        reg = _register([
            _entry(2, "2026-05-01", homework="資料作成", owner="山田", deadline="2026-05-10"),
        ])
        res = build_prep(reg, as_of="2026-05-01")
        ev = res.checklist[0].evidence
        assert "E" in {c.column for c in ev}      # 宿題_内容
        assert any('資料作成' in c.render() for c in ev)


# ===========================================================================
# AC-6: upcoming_task（--wbs 時のみ・窓内に開始or終了）
# ===========================================================================

class TestUpcomingTask:
    def test_count(self, prep_sample_wbs, sample_upcoming_task):
        up = [i for i in prep_sample_wbs.checklist if i.kind == "upcoming_task"]
        assert len(up) == sample_upcoming_task

    def test_all_due_soon(self, prep_sample_wbs):
        up = [i for i in prep_sample_wbs.checklist if i.kind == "upcoming_task"]
        assert up
        assert all(i.status == "due_soon" for i in up)

    def test_not_generated_without_wbs(self, prep_sample):
        assert not any(i.kind == "upcoming_task" for i in prep_sample.checklist)

    def test_window_is_closed_interval(self):
        reg = _register([_entry(2, "2026-06-01", mtype="定例")])
        # as_of=2026-06-01, horizon=14 → 窓 [06-01, 06-15]。
        wv = _wbs([
            {"id": "A", "row": 2, "end": "2026-06-15", "phase": "P1"},   # 上端=窓内
            {"id": "B", "row": 3, "end": "2026-06-16", "phase": "P1"},   # 窓外
            {"id": "C", "row": 4, "start": "2026-06-01", "phase": "P1"}, # 下端=窓内（着手）
        ])
        res = build_prep(reg, as_of="2026-06-01", horizon_days=14, wbs_view=wv)
        up_ids = {i.related_tasks[0] for i in res.checklist if i.kind == "upcoming_task"}
        assert up_ids == {"A", "C"}


# ===========================================================================
# AC-7 / S-1: WBS有無で carryover/decision/freshness 不変・差分=upcoming/related_phases
# ===========================================================================

class TestWbsInvariance:
    def test_item_count_with_wbs(self, prep_sample_wbs, sample_item_count_with_wbs):
        assert prep_sample_wbs.summary["item_count"] == sample_item_count_with_wbs

    def test_three_kinds_identity_unchanged(self, minutes_sample_path, wbs_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        wv = read_wbs(str(wbs_sample_path))
        r0 = build_prep(reg)
        r1 = build_prep(reg, wbs_view=wv)

        def ids(res):
            return [(i.kind, i.status, i.title, i.due, i.owner)
                    for i in res.checklist
                    if i.kind in ("carryover_action", "decision_followup", "freshness")]
        assert ids(r0) == ids(r1)

    def test_item_count_diff_is_upcoming(
        self, prep_sample, prep_sample_wbs, sample_upcoming_task
    ):
        diff = prep_sample_wbs.summary["item_count"] - prep_sample.summary["item_count"]
        assert diff == sample_upcoming_task

    def test_related_phases_none_without_wbs_list_with(
        self, minutes_sample_path, wbs_sample_path
    ):
        reg = read_minutes(str(minutes_sample_path))
        wv = read_wbs(str(wbs_sample_path))
        r0 = build_prep(reg)
        r1 = build_prep(reg, wbs_view=wv)
        cd0 = [i for i in r0.checklist if i.kind in ("carryover_action", "decision_followup")]
        cd1 = [i for i in r1.checklist if i.kind in ("carryover_action", "decision_followup")]
        assert all(i.related_phases is None for i in cd0)
        assert all(isinstance(i.related_phases, list) for i in cd1)
        # 少なくとも1件は工程が突合できている。
        assert any(i.related_phases for i in cd1)


# ===========================================================================
# AC-9: freshness（議事録 days_since>stale_days で発火・既定as_ofで不発火）
# ===========================================================================

class TestFreshness:
    def test_not_fired_at_default_as_of(self, prep_sample):
        assert not any(i.kind == "freshness" for i in prep_sample.checklist)

    def test_fires_when_as_of_pushed(self, minutes_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        # 最新会議日 2026-07-10 から 30日超後ろ倒し（=53日）。
        res = build_prep(reg, as_of="2026-09-01")
        fr = [i for i in res.checklist if i.kind == "freshness"]
        assert len(fr) == 1
        assert fr[0].status == "info"
        assert res.notice is not None and res.notice.get("stale_minutes") == 53

    def test_stale_days_threshold(self):
        reg = _register([_entry(2, "2026-05-01", mtype="定例")])
        # days_since=10 < 30 → 不発火。
        r_no = build_prep(reg, as_of="2026-05-11", stale_days=30)
        assert not any(i.kind == "freshness" for i in r_no.checklist)
        # stale_days=5 にすると days_since=10>5 → 発火。
        r_yes = build_prep(reg, as_of="2026-05-11", stale_days=5)
        assert any(i.kind == "freshness" for i in r_yes.checklist)


# ===========================================================================
# AC-17 / S-4: meeting_scope（指定=部分集合・未指定=全件・upcomingは全件）
# ===========================================================================

class TestMeetingScope:
    def test_scope_field_all_when_unspecified(self, prep_sample_wbs):
        assert prep_sample_wbs.meeting_scope == "all"

    def test_scope_field_set_when_specified(self, minutes_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        types = [e.meeting_type for e in reg.entries if e.meeting_type]
        t = types[0]
        res = build_prep(reg, meeting_type=t)
        assert res.meeting_scope == t

    def test_scope_is_subset_and_upcoming_full(self, minutes_sample_path, wbs_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        wv = read_wbs(str(wbs_sample_path))
        all_res = build_prep(reg, wbs_view=wv)
        all_cd = {(i.kind, i.title) for i in all_res.checklist
                  if i.kind in ("carryover_action", "decision_followup")}
        up_all = len([i for i in all_res.checklist if i.kind == "upcoming_task"])

        for t in sorted({e.meeting_type for e in reg.entries if e.meeting_type}):
            res = build_prep(reg, wbs_view=wv, meeting_type=t)
            cd = {(i.kind, i.title) for i in res.checklist
                  if i.kind in ("carryover_action", "decision_followup")}
            assert cd <= all_cd                                   # 部分集合（S-4）
            up = len([i for i in res.checklist if i.kind == "upcoming_task"])
            assert up == up_all                                   # upcoming は会議体非依存で全件（§15）


# ===========================================================================
# AC-19: unknown_tasks（議事録の関連タスクが WBS 未存在）・突合スキップ続行
# ===========================================================================

class TestUnknownTasks:
    def test_unknown_recorded_and_no_crash(self):
        reg = _register([
            _entry(2, "2026-05-01", homework="設計レビュー", deadline="2026-05-03",
                   related_tasks=["T01", "T99"]),
        ])
        wv = _wbs([{"id": "T01", "row": 2, "phase": "P1", "name": "要件定義"}])
        res = build_prep(reg, as_of="2026-05-03", wbs_view=wv)
        assert res.notice is not None
        assert res.notice.get("unknown_tasks") == ["T99"]
        carry = [i for i in res.checklist if i.kind == "carryover_action"][0]
        assert carry.related_phases == ["P1"]      # 既知 T01 は突合・未知 T99 はスキップ

    def test_no_notice_when_clean(self, prep_sample_wbs):
        # サンプルは未知タスク無し・既定as_ofで freshness 無し → notice None（AC-13 全空null）。
        assert prep_sample_wbs.notice is None


# ===========================================================================
# AC-18: deepcopy 冪等・入力非破壊
# ===========================================================================

class TestIdempotent:
    def test_repeated_run_equal(self, minutes_sample_path, wbs_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        wv = read_wbs(str(wbs_sample_path))
        r1 = build_prep(reg, wbs_view=wv)
        r2 = build_prep(reg, wbs_view=wv)
        assert r1 == r2

    def test_input_not_mutated(self, minutes_sample_path, wbs_sample_path):
        reg = read_minutes(str(minutes_sample_path))
        wv = read_wbs(str(wbs_sample_path))
        before_entries = copy.deepcopy(reg.entries)
        before_rows = copy.deepcopy(wv.rows)
        build_prep(reg, wbs_view=wv)
        assert reg.entries == before_entries
        assert wv.rows == before_rows
