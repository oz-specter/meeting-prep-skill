"""会議準備チェックリスト生成コア（G5: 議事録だけで動く核）.

仕様: specs/meeting-prep.md §3（区分→status付与）・§3.2（閉区間 status）・§3.3（並び）・
§5/§5.1（出力/推奨）・§8（不変条件）・§10（アンカー A-4/A-5/A-8）。

新規コア（D3固有・複製でなく設計）。複製元（D1 minutes_reader/model/config・workcal）の
ロジックは改変せず**呼ぶだけ**。

G5スコープ（議事録のみ）:
  - carryover_action（宿題非空の全件・完了は推測しない・★#4・AC-3）。
  - decision_followup（決定事項に RK-/R- 参照を含む決定・AC-5）。
  - status 付与（§3.2 閉区間・AC-4/S-2）・並び（§3.3 安定・AC-8/S-5）。
  - headline / summary / recommended_actions（§5/§5.1・AC-12）・evidence（CellRef・AC-10）。
  - deepcopy 冪等・now() 禁止（AC-18）。

G6スコープ（本ファイルに上積み・本ファイルの carryover/decision/並びは G6 で不変＝S-1の素地）:
  - upcoming_task（WBS由来）・各項目への related_phases enrich・freshness・meeting_scope。

非交渉ライン（CLAUDE.md 不変条件・spec §8）:
  - now()/today() を分析パスで使わない（決定論・AC-18）。
  - 入力 register を破壊しない（deepcopy で作業＝冪等・AC-18）。
  - status語彙・horizon・参照正規表現・書式を決め打ちしない（config 可変）。
  - evidence は CellRef 由来（view.cellref 経由・手組み禁止・ref==render()・AC-10）。
  - 自由文生成なし（headline/recommended_actions は config 書式＋実測値の埋め込みのみ・§8-5）。
"""

from __future__ import annotations

import copy
import datetime as _dt
import re
from dataclasses import dataclass, field

from . import config as _config_mod
from .workcal import iso_week_label

# 同一議事録行から複数項目が出るときの並びタイブレーク（決定論・kind固定順）。
_KIND_TIEBREAK: dict[str, int] = {
    "carryover_action": 0,
    "decision_followup": 1,
    "upcoming_task": 2,
    "freshness": 3,
}


# ---------------------------------------------------------------------------
# 公開データクラス（G5 IF・G6 は related_phases を充填）
# ---------------------------------------------------------------------------

@dataclass
class ChecklistItem:
    """チェックリスト1項目（spec §5 checklist 要素の素地）.

    related_phases は G6（WBS突合）で付与。G5 では None。
    excel_row / _due_date は並びの intrinsic キー（入力リスト順に非依存＝S-5）。
    """

    kind: str                                        # carryover_action | decision_followup
    status: str                                      # overdue | due_soon | pending | info
    title: str
    owner: str
    due: str                                         # "YYYY-MM-DD" or ""
    related_tasks: list = field(default_factory=list)
    evidence: list = field(default_factory=list)     # CellRef（view.cellref 由来）
    related_phases: "list | None" = None             # G6 で付与
    excel_row: int = 0                               # 出現順キー（議事録の実Excel行）
    _due_date: "_dt.date | None" = None              # 期日キー（並び用・内部）


@dataclass
class PrepResult:
    """build_prep の返り値（prep_checklist payload の素地）."""

    as_of: str                                       # "YYYY-MM-DD"
    as_of_week: str                                  # "YYYY-Www"
    horizon_days: int
    meeting_scope: str                               # G5 は "all"（scope は G6）
    headline: str
    checklist: list                                  # ChecklistItem を §3.3 並びで
    summary: dict                                    # {item_count, by_status, by_kind}
    overdue_note: str
    recommended_actions: list


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
    """col_letter に在る列のみ CellRef を起こす（手組み禁止・view.cellref 経由・§8-4）.

    列が台帳に無い（任意列が議事録に存在しない）場合は None を返す。
    """
    if canon not in view.col_letter:
        return None
    return view.cellref(canon, entry.excel_row, value, note=note)


# ---------------------------------------------------------------------------
# 公開 API
# ---------------------------------------------------------------------------

def build_prep(
    minutes_register,
    *,
    config=_config_mod,
    as_of: "str | _dt.date | None" = None,
    horizon_days: "int | None" = None,
) -> PrepResult:
    """議事録から会議準備チェックリスト（PrepResult）を組む（非破壊・決定論・G5スコープ）.

    Args:
        minutes_register: minutes_reader.read_minutes() の成功時返り値（MinutesRegister）。
        config: status語彙・horizon・参照正規表現・書式の供給元（既定 src.config）。
        as_of: --as-of 明示値（str ISO / date）。None なら議事録の最新会議日（§2.1）。
        horizon_days: due_soon 窓の地平線。None なら config.HORIZON_DAYS（14）。

    Returns:
        PrepResult（G5: carryover_action / decision_followup・status・並び・headline・
        summary・recommended_actions・evidence）。

    Raises:
        ValueError: as_of を決定できないとき（--as-of 明示も議事録会議日も無い）。
    """
    # 非破壊: 入力 register を deepcopy（AC-18・冪等）。
    minutes_register = copy.deepcopy(minutes_register)
    view = minutes_register.view

    horizon = horizon_days if horizon_days is not None else config.HORIZON_DAYS

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

    ref_pattern = re.compile(config.DECISION_REF_PATTERN)

    items: list[ChecklistItem] = []

    # -----------------------------------------------------------------
    # 区分枚挙（議事録の入力出現順に走査）。
    # -----------------------------------------------------------------
    for entry in minutes_register.entries:
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
            items.append(ChecklistItem(
                kind="carryover_action",
                status=status,
                title=entry.homework_content,
                owner=entry.homework_owner,
                due=entry.deadline_str,
                related_tasks=list(entry.related_tasks),
                evidence=evidence,
                excel_row=entry.excel_row,
                _due_date=entry.deadline,
            ))

        # --- decision_followup（決定に RK-/R- 参照を含む・status=pending・AC-5）---
        if entry.decision and ref_pattern.search(entry.decision):
            evidence = []
            c = _entry_cellref(view, "決定事項", entry, entry.decision, "決定")
            if c is not None:
                evidence.append(c)
            items.append(ChecklistItem(
                kind="decision_followup",
                status="pending",
                title=entry.decision,
                owner="",
                due="",
                related_tasks=list(entry.related_tasks),
                evidence=evidence,
                excel_row=entry.excel_row,
                _due_date=None,
            ))

    # -----------------------------------------------------------------
    # 並び（§3.3・AC-8/S-5）:
    #   status優先 → 期日昇順（なしは末尾）→ 出現順（excel_row）→ kind固定順。
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
    #   G5 では upcoming_task / freshness は未生成（0件）＝該当分岐は不発火。
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
    # freshness 分岐は G6（議事録鮮度）で追加。

    return PrepResult(
        as_of=as_of_str,
        as_of_week=as_of_week,
        horizon_days=horizon,
        meeting_scope="all",
        headline=headline,
        checklist=items,
        summary=summary,
        overdue_note=config.OVERDUE_NOTE,
        recommended_actions=recommended,
    )
