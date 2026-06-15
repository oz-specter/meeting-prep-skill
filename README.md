# meeting-prep-skill（D3 会議事前準備 / ui_type=prep_checklist）

議事録(.xlsx)＋任意WBS(.xlsx)から、**次の会議までに片付ける／議題化すべき事項**を
決定論でチェックリスト化し、A1互換エンベロープ（`ui_type=prep_checklist`・確定UI型9種目）で出す。
ウェーブ2・1 skill=1 repo。唯一の真実は [`specs/meeting-prep.md`](specs/meeting-prep.md)。

## 使い方
```
python src/cli.py --minutes <議事録.xlsx> [--wbs <WBS.xlsx>] \
  --out _output/ --format md|html|json|csv|envelope \
  [--project-name 名] [--as-of YYYY-MM-DD] [--horizon-days 14] [--meeting-type 会議体] [--stale-days 30]
```

## チェックリスト4区分
carryover_action（未消込宿題）/ decision_followup（RK-・R-参照の決定）/
upcoming_task（`--wbs`時・horizon窓内のWBSタスク）/ freshness（議事録鮮度）。
status＝overdue / due_soon / pending / info。

## D1（report-skill）との違い
D1=後ろ向きの週次ステークホルダー報告（summary_links）。D3=前向きの会議準備チェックリスト＋
WBSの直近着手/期限タスクを議題候補として前出し（upcoming_task）。

## 開発
[`CLAUDE.md`](CLAUDE.md) 参照。`pytest tests/` で全緑。CIは2本柱（pytest照合＋sha256マニフェスト）、
境界再現スクリプト（3本柱目）はCLI完成ゲートG7で追加。複製元: D1 report-skill / C2 risk-response-skill / B1 progress-skill。
