"""議事録スキーマの正規化辞書＋D3固有設定（specs §2/§3/§5/§10・論点#11）.

設計上の役割:
  - 議事録の列名揺れ・シート名揺れを一か所に集約（既存資産AIラッピングの中核）。
  - minutes_reader はこのモジュールの辞書を参照し重複実装しない。
  - status語彙・horizon・参照正規表現・書式は定数として外から差し替え可能（決め打ち禁止）。

I/O なし・openpyxl なし・時刻/乱数なし（純データ＋純関数）。決定論的。

構成:
  - 前半「議事録スキーマ」は **D1 report-skill/src/config.py の議事録部を逐語複製（D1部改変禁止）**。
  - 後半「D3固有」は D3 で追記（status/horizon/参照正規表現/書式/並び）。
  - D3 は進捗報告を入力に取らないため、B1進捗スキーマ部（COLUMN_ALIASES/DELAY_*）は持ち込まない。
"""

from __future__ import annotations

# ===========================================================================
# 議事録スキーマ（D1複製・改変禁止。由来: D1 report-skill/src/config.py §2）
# ===========================================================================

# シート名の読み替え（議事録）。
MINUTES_SHEET_ALIASES: dict[str, list[str]] = {
    "議事録": ["議事録", "会議議事録", "ミーティング議事録", "MTG議事録", "会議録"],
}

# 列名揺れ吸収辞書（議事録）: 正規化名 -> 同義表記のリスト（正規名を先頭に自己包含）。
MINUTES_COLUMN_ALIASES: dict[str, list[str]] = {
    "日付":       ["日付", "会議日", "開催日", "実施日", "日時"],
    "会議体":     ["会議体", "会議名", "会議種別", "ミーティング", "会議"],
    "決定事項":   ["決定事項", "決定", "決定内容", "決議事項"],
    "出席":       ["出席", "出席者", "参加者", "参加"],
    "宿題_内容":  ["宿題_内容", "宿題内容", "宿題", "アクション", "ToDo"],
    "宿題_担当":  ["宿題_担当", "宿題担当", "担当", "担当者"],
    "宿題_期限":  ["宿題_期限", "宿題期限", "期限", "締切", "期日"],
    "関連タスク": ["関連タスク", "関連タスクID", "タスクID", "関連task"],
    "関連要件":   ["関連要件", "関連要件ID", "要件ID", "要件"],
}

# 必須列・任意列（議事録・spec §2）。
MINUTES_REQUIRED_COLUMNS: list[str] = ["日付", "会議体", "決定事項"]
MINUTES_OPTIONAL_COLUMNS: list[str] = [
    "出席", "宿題_内容", "宿題_担当", "宿題_期限", "関連タスク", "関連要件",
]


def normalize_minutes_column(raw: object) -> str | None:
    """議事録ヘッダ表記 -> 正規列名。前後空白除去・大文字小文字無視で素朴一致。未知は None。

    由来: D1 report-skill/src/config.py の normalize_minutes_column 逐語複製。
    """
    if not raw or not isinstance(raw, str):
        return None
    normalized = raw.strip().lower()
    for canonical, aliases in MINUTES_COLUMN_ALIASES.items():
        for alias in aliases:
            if alias.strip().lower() == normalized:
                return canonical
    return None


# 議事録の鮮度しきい値（日。D1複製・spec §2.1 freshness）。
# (as_of − 議事録日付max).days > これ で freshness 項目＋notice.stale_minutes 発火。
STALE_MINUTES_DAYS: int = 30


# ===========================================================================
# D3 固有（specs §3/§5/§10・論点#11。config 可変＝決め打ち禁止）
# ===========================================================================

# --- horizon（spec §2.1） ---
# due_soon 窓は閉区間 [as_of, as_of + HORIZON_DAYS]。
HORIZON_DAYS: int = 14

# --- status 語彙（spec §3.2・固定4値・識別子は機械判別／ラベルは表示用） ---
STATUS_LABELS: dict[str, str] = {
    "overdue": "期限経過",
    "due_soon": "期限間近",
    "pending": "未確認",
    "info": "参考",
}

# 並び優先度（spec §3.3。小さいほど上位）。
STATUS_ORDER: dict[str, int] = {
    "overdue": 0,
    "due_soon": 1,
    "pending": 2,
    "info": 3,
}

# --- 区分（kind）語彙（spec §3.1。表示用ラベル） ---
KIND_LABELS: dict[str, str] = {
    "carryover_action": "宿題（持ち越し）",
    "decision_followup": "決定フォロー",
    "upcoming_task": "直近タスク",
    "freshness": "鮮度",
}

# --- decision_followup の参照抽出（spec §3.1・★#2）。RK-数字 / R-数字 を拾う。 ---
DECISION_REF_PATTERN: str = r"(RK-\d+|R-\d+)"

# --- 書式（spec §5 headline・§5.1 recommended_actions・自由文生成なし＝テンプレ＋実測値） ---
# headline: 要対応がある場合 / 全０件（green相当）の場合。
HEADLINE_FORMAT: str = "次回までに要対応 {item_count}件（期限経過{overdue}・期限間近{due_soon}）"
HEADLINE_FORMAT_EMPTY: str = "次回までに要対応の項目はありません"

# recommended_actions（spec §5.1・決定論固定順）。
RECOMMENDED_ACTION_TEMPLATES: dict[str, str] = {
    "overdue": "期限経過の宿題 {n}件の状況を次回会議で確認",
    "upcoming": "{horizon}日以内に着手/期限の {n}タスクを議題化",
    "decision": "決定に紐づくリスク/要件 {n}件の進捗を確認",
    "freshness": "議事録が {days}日更新なし・最新化を依頼",
}

# overdue_note（spec §5・★#4。完了状態は推測しない＝事実提示のみ）。
OVERDUE_NOTE: str = "※完了状態は議事録に記録がありません（期限経過は事実の提示のみ）"
