---
name: meeting-prep-skill
description: 議事録(.xlsx)と任意のWBS(.xlsx)から、次の会議までに片付ける／次の議題に載せるべき事項を決定論でチェックリスト化する。宿題の持ち越し（期限経過/期限間近）、決定のフォロー（RK-/R-参照）、WBSの直近着手/期限タスクの前出しを、根拠セル参照つきで出力する。「会議準備」「次回までに」「宿題の消し込み」「議題候補」「prep checklist」のときに使う。
---

# 会議事前準備スキル（meeting-prep-skill）

## 何をするか

議事録（必須）と WBS（任意）を読み、**次の会議に向けたチェックリスト**を決定論で生成する。

- **carryover_action**: 宿題が未記入でない全件を持ち越し項目に（完了状態は推測しない＝事実提示のみ）。期限で `overdue / due_soon / pending` に分類。
- **decision_followup**: 決定事項に `RK-数字` / `R-数字` の参照を含むものをフォロー対象に。
- **upcoming_task**（`--wbs` 時）: 開始日 or 終了日が「いま～horizon日先」の窓に入る WBS タスクを議題候補として前出し。
- **freshness**: 議事録が `stale-days`（既定30日）より古いと最新化を促す。
- すべての項目に **Excelセル参照（根拠）** を付ける。AIの自由文生成はしない（テンプレ＋実測値）。

## 使い方

```
python src/cli.py --minutes <議事録.xlsx> [--wbs <WBS.xlsx>] \
    --out _output/ --format md|html|json|csv|envelope \
    [--project-name 名] [--as-of YYYY-MM-DD] [--horizon-days 14] \
    [--meeting-type 会議体] [--stale-days 30]
```

- `--project-name` は**明示渡しを推奨**（ダッシュボード統合の grouping キー・正準名）。未指定時は議事録ファイル名 stem。
- `--as-of` 既定 = 議事録の最新会議日（データ由来）。`--horizon-days` 既定 14（due_soon 窓は閉区間 `[as_of, as_of+horizon]`）。
- `--meeting-type` 指定時は carryover/decision を当該会議体に絞る（**upcoming_task は会議体非依存で全件**）。

## 入力の前提

- 議事録シート必須列 `日付 / 会議体 / 決定事項`、任意列 `出席 / 宿題_内容 / 宿題_担当 / 宿題_期限 / 関連タスク / 関連要件`。
- WBS シート最小必須列 `タスクID / タスク名`、任意 `担当 / 開始日 / 終了日 / 工程`。
- 列名・シート名の揺れは `src/config.py` の別名辞書で吸収する（**Excel側を直す必要はない**）。

## 出力

- `_output/会議準備チェックリスト_YYYYMMDD_HHMMSS.<ext>`（envelope は `.envelope.json`）＋ `history.jsonl` 追記。
- **CSV** は UTF-8 BOM 付き・1項目1行・固定9列 `プロジェクト, 区分, 状態, 項目, 担当, 期日, 関連タスク, 関連工程, 根拠セル参照`。
- **envelope** は A1 互指10キー・`ui_type=prep_checklist`（統合ダッシュボードの確定UI型9種目）。
- exit コード: `0`=正常 / `2`=必須列・シート欠落 / その他=異常。必須欠落でも `--format envelope` は `status=degraded` で exit0（手当て提案を返す）。

## 設計原則

決定論（同一入力＝同一出力・`now()` は出力スタンプ専用）／既存資産AIラッピング（Excelを書き換えない）／説明可能性（全項目に CellRef）／自由文生成なし。複製元（D1 report-skill・C2 risk-response-skill・B1 progress-skill）の振る舞いは改変しない。
