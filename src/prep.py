"""会議準備チェックリスト生成コア（G5: 議事録の核 ＋ G6: WBS依存の上積み）.

仕様: specs/meeting-prep.md §2.1（as_of/freshness）・§3（区分→status）・§3.2（閉区間）・
§3.3（並び）・§4（WBS突合）・§5/§5.1（出力/推奨）・§7/§15（meeting_scope）・§8（不変条件）・
§10（アンカー A-4/A-5/A-6/A-7/A-8/A-9）。

新規コア（D3固有・複製でなく設計）。複製元（D1 minutes_reader/model/config・workcal・
C2 wbs_reader）のロジックは改変せず**呼ぶだけ**。

G5スコープ（議事録のみ・本ファイルで不変＝S-1差分検証の素地）:
  - carryover_action（宿題非空の全件・完了は推測しない・★#4・AC-3）。
  - decision_followup（決定に RK-/R- 参照・status=pending・AC-5）。
  - status 付与（§3.2 閉区間・AC-4/S-2）・並び（§3.3 安定・AC-8/S-5）。
  - headline / summary / recommended_actions（§5/§5.1・AC-12）・evidence（CellRef・AC-10）。
  - deepcopy 冪等・now() 禁止（AC-18）。

G6スコープ（WBS依存を上積み）:
  - upcoming_task（--wbs時のみ・開始日/終了日が due_soon 窓内・AC-6）。
  - carryover/decision への related_phases enrich＋WBS工程 evidence（§4・AC-7 の差分）。
  - freshness（議事録 days_since>stale_days・status=info・AC-9）。
  - meeting_scope（--meeting-type で carryover/decision を会議体一致フィルタ・upcoming は全件・§15・AC-17/S-4）。
  - unknown_tasks（議事録の関連タスクが WBS 未存在）を notice に記録し突合スキップ続行（AC-19）。

非交渉ライン（CLAUDE.md 不変条件・spec §8）:
  - now()/today() を分析パスで使わない（決定論・AC-18）。
  - 入力 register / wbs_view を破壊しない（deepcopy で作業＝冪等・AC-18）。
  - status語彙・horizon・参照正規表現・書式を決め打ちしない（config 可変）。
  - evidence は CellRef 由来（view.cellref / wbs_view.task_cellref 経由・手組み禁止・ref==render()・AC-10）。
  - 自由文生成なし（headline/recommended_actions/freshness題は config 書式＋実測値の埋め込みのみ・§8-5）。
"""

from __future__ import annotations

import copy
import datetime as _dt
import re
from dataclasses import dataclass, field

from . import config as _config_mod
from .workcal import iso_week_label

# 並びの「出現順」ソース順位（§3.3: 議事録行 → WBS行）。
_SOURCE_MINUTES = 0
_SOURCE_WBS = 1

# 同一行から複数項目が出るときの並びタイブレーク（決定論・kind固定順）。
_KIND_TIEBREAK: dict[str, int] = {
    "carryover_action": 0,
    "decision_followup": 1,
    "upcoming_task": 2,
    "freshness": 3,
}


# ---------------------------------------------------------------------------
# 公開データクラス
# ---------------------------------------------------------------------------

@dataclass
class ChecklistItem:
    """チェックリスト1項目（spec §5 checklist 要素の素地）.

    related_phases は --wbs 時のみ list（無WBSは None＝S-1の差分の所在）。
    excel_row / source_rank / _due_date は並びの intrinsic キー（入力リスト順に非依存＝S-5）。
    """

    kind: str                                        # carryover_action | decision_followup | upcoming_task | freshness
    status: str                                      # overdue | due_soon | pending | info
    title: str
    owner: str
    due: str                                         # "YYYY-MM-DD" or ""
    related_tasks: list = field(default_factory=list)
    evidence: list = field(default_factory=list)     # CellRef（cellref / task_cellref 由来）
    related_phases: "list | None" = None             # --wbs 時のみ list
    excel_row: int = 0                               # 出現順キー（実Excel行）
    source_rank: int = _SOURCE_MINUTES               # 0=議事録由来 / 1=WBS由来
    _due_date: "_dt.date | None" = None              # 期日キー（並び用・内部）


@dataclass
class PrepResult:
    """build_prep の返り値（prep_checklist payload の素地）."""

    as_of: str                                       # "YYYY-MM-DD"
    as_of_week: str                                  # "YYYY-Www"
    horizon_days: int
    meeting_scope: str                               # "<会議体>" | "all"
    headline: str
    checklist: list                                  # ChecklistItem を §3.3 並びで
    summary: dict                                    # {item_count, by_status, by_kind}
    overdue_note: str
    recommended_actions: list
    notice: "dict | None" = None                     # 非空フィールドのみ・全空 None（§6・AC-13）


# ---------------------------------------------------------------------------
# 内部ヘルパ（純関数・複製元を触らない）
# ---------------------------------------------------------------------------

def _coerce_as_of(as_of_arg: "str | _dt.date | None") -> "_dt.date | None":
    """--as-of 引数（str ISO / date / datetime / None）を date に解決する（None はそのまま）."""
    if as_of_arg is None:
        return None
    if isinstance(as_of_arg, _dt.datetime):
        return as_of_arg.date()
    if isinstance(as_of_arg, _dt.date):
        return as_of_arg
    try:
        return _dt.date.fromisoformat(str(as_of_arg).strip())
    except ValueError:
        return None


def _coerce_date(value) -> "_dt.date | None":
    """WBS セル生値（datetime / date / str）→ date。パース不能・空は None（例外なし）.

    minutes_reader._parse_date と同方針（datetime を date より先に判定・"%Y-%m-%d"/"%Y/%m/%d"）。
    """
    if value is None:
        return None
    if isinstance(value, _dt.datetime):
        return value.date()
    if isinstance(value, _dt.date):
        return value
    if isinstance(value, str):
        s = value.strip()
        if not s or s == "-":
            return None
        for fmt in ("%Y-%m-%d", "%Y/%m/%d"):
            try:
                return _dt.datetime.strptime(s, fmt).date()
            except ValueError:
                pass
    return None


def _status_for_deadline(
    deadline: "_dt.date | None",
    as_of_date: _dt.date,
    horizon_days: int,
) -> str:
    """宿題期限 -> status（spec §3.2・固定4値・閉区間・AC-4/S-2）.

    deadline <= as_of                      -> overdue（as_of 当日は overdue 側）
    as_of < deadline <= as_of + horizon    -> due_soon（窓は閉区間・上端含む）
    それ以外（窓より後）/ 期限なし          -> pending
    """
    if deadline is None:
        return "pending"
    if deadline <= as_of_date:
        return "overdue"
    if deadline <= as_of_date + _dt.timedelta(days=horizon_days):
        return "due_soon"
    return "pending"


def _entry_cellref(view, canon: str, entry, value, note: str):
    """議事録 col_letter に在る列のみ CellRef を起こす（手組み禁止・view.cellref 経由・§8-4）."""
    if canon not in view.col_letter:
        return None
    return view.cellref(canon, entry.excel_row, value, note=note)


def _wbs_value(wbs_view, task_id: str, canon: str):
    """WBS の (task_id, 正規列) の生値を返す（task_cellref 経由・列/タスク無→None）."""
    cref = wbs_view.task_cellref(task_id, canon)
    return cref.value if cref is not None else None


def _enrich_with_wbs(item: ChecklistItem, wbs_view, unknown_tasks: "set[str]") -> None:
    """carryover/decision 項目に related_phases（工程）と WBS工程 evidence を付与（§4・AC-7）.

    - 未知 task_id は unknown_tasks に記録し突合スキップ（AC-19）。
    - 工程列欠落・該当工程なしは related_phases=[]（クラッシュ禁止・AC-19）。
    - related_phases は --wbs 時は必ず list（無WBSの None と区別＝S-1の差分の所在）。
    """
    phases: set[str] = set()
    phase_crefs: list = []
    for tid in item.related_tasks:
        if tid not in wbs_view.rows:
            unknown_tasks.add(tid)
            continue
        cref = wbs_view.task_cellref(tid, "工程", note="工程")
        if cref is not None and cref.value not in (None, ""):
            phases.add(str(cref.value))
            phase_crefs.append(cref)
    item.related_phases = sorted(phases)
    for c in sorted(phase_crefs, key=lambda c: str(c.value)):
        item.evidence.append(c)


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def build_prep(
    minutes_register,
    *,
    wbs_view=None,
    config=_config_mod,
    as_of: "str | _dt.date | None" = None,
    horizon_days: "int | None" = None,
    stale_days: "int | None" = None,
    meeting_type: "str | None" = None,
) -> PrepResult:
    """議事録（＋任意WBS）から会議準備チェックリスト（PrepResult）を組む（非破壊・決定論）.

    Args:
        minutes_register: minutes_reader.read_minutes() の成功時返り値（MinutesRegister）。
        wbs_view: wbs_reader.read_wbs() の成功時返り値（WbsView）。None なら WBS 連携なし。
        config: status語彙・horizon・参照正規表現・書式の供給元（既定 src.config）。
        as_of: --as-of 明示値（str ISO / date）。None なら議事録の最新会議日（§2.1）。
        horizon_days: due_soon 窓の地平線。None なら config.HORIZON_DAYS（14）。
        stale_days: freshness 判定日数。None なら config.STALE_MINUTES_DAYS（30）。
        meeting_type: --meeting-type。指定時は carryover/decision を会議体一致でフィルタ
            （upcoming_task は会議体非依存で全件・§15）。

    Returns:
        PrepResult。

    Raises:
        ValueError: as_of を決定できないとき（--as-of 明示も議事録会議日も無い）。
    """
    # 非破壊: 入力を deepcopy（AC-18・冪等）。
    minutes_register = copy.deepcopy(minutes_register)
    wbs_view = copy.deepcopy(wbs_view)
    view = minutes_register.view

    horizon = horizon_days if horizon_days is not None else config.HORIZON_DAYS
    stale_days_val = stale_days if stale_days is not None else config.STALE_MINUTES_DAYS

    # -----------------------------------------------------------------
    # as_of 規約（§2.1）: 明示 > 議事録の最新会議日。
    # -----------------------------------------------------------------
    explicit_as_of = _coerce_as_of(as_of)
    if explicit_as_of is not None:
        as_of_date = explicit_as_of
    else:
        as_of_date = minutes_register.max_meeting_date()

    if as_of_date is None:
        raise ValueError(
            "as_of を決定できません（--as-of 明示・議事録の会議日のいずれも無し）"
        )

    as_of_str = as_of_date.isoformat()
    as_of_week = iso_week_label(as_of_date)
    window_end = as_of_date + _dt.timedelta(days=horizon)

    ref_pattern = re.compile(config.DECISION_REF_PATTERN)

    items: list[ChecklistItem] = []
    unknown_tasks: set[str] = set()

    # -----------------------------------------------------------------
    # 議事録由来の区分（carryover_action / decision_followup）。
    #   meeting_scope: meeting_type 指定時は会議体一致のみ（§15・AC-17/S-4）。
    # -----------------------------------------------------------------
    for entry in minutes_register.entries:
        if meeting_type is not None and entry.meeting_type != meeting_type:
            continue

        # --- carryover_action（宿題非空の全件・完了は推測しない・★#4・AC-3）---
        if entry.homework_content:
            status = _status_for_deadline(entry.deadline, as_of_date, horizon)
            evidence: list = []
            c = _entry_cellref(view, "宿題_内容", entry, entry.homework_content, "宿題")
            if c is not None:
                evidence.append(c)
            if entry.homework_owner:
                c = _entry_cellref(view, "宿題_担当", entry, entry.homework_owner, "担当")
                if c is not None:
                    evidence.append(c)
            if entry.deadline_str:
                c = _entry_cellref(view, "宿題_期限", entry, entry.deadline_raw, "期限")
                if c is not None:
                    evidence.append(c)
            item = ChecklistItem(
                kind="carryover_action",
                status=status,
                title=entry.homework_content,
                owner=entry.homework_owner,
                due=entry.deadline_str,
                related_tasks=list(entry.related_tasks),
                evidence=evidence,
                excel_row=entry.excel_row,
                source_rank=_SOURCE_MINUTES,
                _due_date=entry.deadline,
            )
            if wbs_view is not None:
                _enrich_with_wbs(item, wbs_view, unknown_tasks)
            items.append(item)

        # --- decision_followup（決定に RK-/R- 参照・status=pending・AC-5）---
        if entry.decision and ref_pattern.search(entry.decision):
            evidence = []
            c = _entry_cellref(view, "決定事項", entry, entry.decision, "決定")
            if c is not None:
                evidence.append(c)
            item = ChecklistItem(
                kind="decision_followup",
                status="pending",
                title=entry.decision,
                owner="",
                due="",
                related_tasks=list(entry.related_tasks),
                evidence=evidence,
                excel_row=entry.excel_row,
                source_rank=_SOURCE_MINUTES,
                _due_date=None,
            )
            if wbs_view is not None:
                _enrich_with_wbs(item, wbs_view, unknown_tasks)
            items.append(item)

    # -----------------------------------------------------------------
    # freshness（議事録由来・--wbs 非依存・§2.1/§3.1・AC-9）。
    #   days_since = (as_of − 最終会議日)。> stale_days で発火・status=info。
    # -----------------------------------------------------------------
    days_since = 0
    last_entry = None
    if minutes_register.entries:
        last_entry = max(minutes_register.entries, key=lambda e: e.meeting_date)
        days_since = (as_of_date - last_entry.meeting_date).days
    freshness_fired = days_since > stale_days_val
    if freshness_fired and last_entry is not None:
        evidence = []
        c = _entry_cellref(view, "日付", last_entry, last_entry.date_raw, "最終会議日")
        if c is not None:
            evidence.append(c)
        items.append(ChecklistItem(
            kind="freshness",
            status="info",
            title=config.RECOMMENDED_ACTION_TEMPLATES["freshness"].format(days=days_since),
            owner="",
            due="",
            related_tasks=[],
            evidence=evidence,
            related_phases=([] if wbs_view is not None else None),
            excel_row=last_entry.excel_row,
            source_rank=_SOURCE_MINUTES,
            _due_date=None,
        ))

    # -----------------------------------------------------------------
    # upcoming_task（--wbs 時のみ・WBS由来・会議体非依存で全件・§3.1/§4/§15・AC-6）。
    #   開始日 or 終了日 が due_soon 窓 [as_of, as_of+horizon] に入るタスク・status=due_soon。
    # -----------------------------------------------------------------
    if wbs_view is not None:
        for task_id, excel_row in wbs_view.rows.items():     # dict は WBS 行順を保持
            start = _coerce_date(_wbs_value(wbs_view, task_id, "開始日"))
            end = _coerce_date(_wbs_value(wbs_view, task_id, "終了日"))
            in_start = start is not None and as_of_date <= start <= window_end
            in_end = end is not None and as_of_date <= end <= window_end
            if not (in_start or in_end):
                continue
            # due は 期限（終了日）優先・無ければ 着手（開始日）。
            due_date = end if in_end else start

            evidence = []
            for canon, note in (("開始日", "開始日"), ("終了日", "終了日"), ("工程", "工程")):
                cref = wbs_view.task_cellref(task_id, canon, note=note)
                if cref is not None and cref.value not in (None, ""):
                    evidence.append(cref)

            phase_val = _wbs_value(wbs_view, task_id, "工程")
            related_phases = [str(phase_val)] if phase_val not in (None, "") else []

            title = _wbs_value(wbs_view, task_id, "タスク名")
            owner = _wbs_value(wbs_view, task_id, "担当")
            items.append(ChecklistItem(
                kind="upcoming_task",
                status="due_soon",
                title=str(title) if title not in (None, "") else task_id,
                owner=str(owner) if owner not in (None, "") else "",
                due=due_date.isoformat() if due_date is not None else "",
                related_tasks=[task_id],
                evidence=evidence,
                related_phases=related_phases,
                excel_row=excel_row,
                source_rank=_SOURCE_WBS,
                _due_date=due_date,
            ))

    # -----------------------------------------------------------------
    # 並び（§3.3・AC-8/S-5）:
    #   status優先 → 期日昇順（なし末尾）→ 出現順（議事録→WBS, source_rank→excel_row）→ kind。
    #   キーは全て intrinsic（入力リストの並び替えに非依存）＝安定ソート。
    # -----------------------------------------------------------------
    def _sort_key(it: ChecklistItem):
        if it._due_date is not None:
            due_key = (0, it._due_date.toordinal())   # 期日あり: 昇順
        else:
            due_key = (1, 0)                            # 期日なし: 末尾
        return (
            config.STATUS_ORDER.get(it.status, 99),
            due_key,
            it.source_rank,
            it.excel_row,
            _KIND_TIEBREAK.get(it.kind, 99),
        )

    items.sort(key=_sort_key)

    # -----------------------------------------------------------------
    # summary（item_count / by_status / by_kind）。
    # -----------------------------------------------------------------
    by_status: dict[str, int] = {"overdue": 0, "due_soon": 0, "pending": 0, "info": 0}
    by_kind: dict[str, int] = {}
    for it in items:
        by_status[it.status] = by_status.get(it.status, 0) + 1
        by_kind[it.kind] = by_kind.get(it.kind, 0) + 1
    item_count = len(items)
    summary = {"item_count": item_count, "by_status": by_status, "by_kind": by_kind}

    # -----------------------------------------------------------------
    # headline（§5・config書式・自由文生成なし）。
    # -----------------------------------------------------------------
    if item_count == 0:
        headline = config.HEADLINE_FORMAT_EMPTY
    else:
        headline = config.HEADLINE_FORMAT.format(
            item_count=item_count,
            overdue=by_status["overdue"],
            due_soon=by_status["due_soon"],
        )

    # -----------------------------------------------------------------
    # recommended_actions（§5.1・決定論固定順・AC-12）。
    #   (1) overdue>0 (2) upcoming>0 (3) decision>0 (4) freshness。
    # -----------------------------------------------------------------
    recommended: list[str] = []
    overdue_n = by_status["overdue"]
    upcoming_n = by_kind.get("upcoming_task", 0)
    decision_n = by_kind.get("decision_followup", 0)
    if overdue_n > 0:
        recommended.append(
            config.RECOMMENDED_ACTION_TEMPLATES["overdue"].format(n=overdue_n)
        )
    if upcoming_n > 0:
        recommended.append(
            config.RECOMMENDED_ACTION_TEMPLATES["upcoming"].format(
                horizon=horizon, n=upcoming_n
            )
        )
    if decision_n > 0:
        recommended.append(
            config.RECOMMENDED_ACTION_TEMPLATES["decision"].format(n=decision_n)
        )
    if freshness_fired:
        recommended.append(
            config.RECOMMENDED_ACTION_TEMPLATES["freshness"].format(days=days_since)
        )

    # -----------------------------------------------------------------
    # notice（§6・AC-13・非空フィールドのみ・全空 None）。
    # -----------------------------------------------------------------
    notice: dict = {}
    if unknown_tasks:
        notice["unknown_tasks"] = sorted(unknown_tasks)
    if freshness_fired:
        notice["stale_minutes"] = days_since
    if minutes_register.unparseable_dates:
        notice["unparseable_dates"] = list(minutes_register.unparseable_dates)
    if minutes_register.unparseable_deadlines:
        notice["unparseable_deadlines"] = list(minutes_register.unparseable_deadlines)

    return PrepResult(
        as_of=as_of_str,
        as_of_week=as_of_week,
        horizon_days=horizon,
        meeting_scope=meeting_type if meeting_type is not None else "all",
        headline=headline,
        checklist=items,
        summary=summary,
        overdue_note=config.OVERDUE_NOTE,
        recommended_actions=recommended,
        notice=(notice if notice else None),
    )
