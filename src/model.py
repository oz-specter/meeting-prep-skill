"""共通中間表現（会議事前準備スキルが扱うデータ構造）.

設計上の中核: 宿題/決定/タスクの根拠を必ず Excelセル参照（CellRef）として保持する。
これが説明可能性の差別化軸（specs/meeting-prep.md §8-4）をデータ構造で担保する仕組み。

複製元: D1 report-skill/src/model.py（CellRef/MissingColumnReport と同型・同シグネチャ）を**逐語複製**。
D1 と同一形（Risk は持たない＝ D3 のスコープ外）。コードは改変しない（由来コメントのみ）。
確定IF: CellRef(sheet, column, row, value, note="") / .render() ／
        MissingColumnReport(sheet, missing_columns, suggestion="")。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class CellRef:
    """Excelセル参照（説明可能性の最小単位）.

    例: CellRef("議事録", "C", 5, "Fit-Gap方針を承認")
        -> render() は `議事録!C5 = "Fit-Gap方針を承認"`
    """

    sheet: str          # シート名（例: "議事録"）
    column: str         # 列記号（例: "C"）または列名
    row: int            # 行番号（1始まり・ヘッダ含む実Excel行）
    value: object       # セルの値
    note: str = ""      # 短い文章解説（任意）

    def render(self) -> str:
        """`[シート名]![列][行] = "[値]"` 形式に整形する."""
        base = f'{self.sheet}!{self.column}{self.row} = "{self.value}"'
        return f"{base} → {self.note}" if self.note else base


@dataclass
class MissingColumnReport:
    """必須列欠落時に reader が返す報告（手当て提案のみ、Excelは直さない）.

    既存資産AIラッピング原則: Excel側の修正は強要しない（specs §2・§8）。
    D1（report-skill）/ A1 の MissingColumnReport と同型。
    """

    sheet: str
    missing_columns: list[str]
    suggestion: str = ""
