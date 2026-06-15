# CLAUDE.md — meeting-prep-skill 開発ガイド（D3 会議事前準備 / ui_type=prep_checklist）

`02_Skill/` 共通レイヤー（親 CLAUDE.md）を自動継承する。本ファイルはこのSkill固有のみ。
唯一の真実は `specs/meeting-prep.md`（AC-1〜20・§15関所１確定事項）。developer/qa はそれを正とする。

## このSkillは何か
議事録(.xlsx)＋任意WBS(.xlsx)から、**次の会議までに片付ける／議題化すべき事項**を決定論で
チェックリスト化する。封筒はA1互換 ui_type=prep_checklist（確定UI型9種目）。4区分＝
carryover_action（未消込宿題）/decision_followup（RK-・R-参照の決定）/upcoming_task（--wbs時・
horizon窓内のWBSタスク）/freshness（議事録鮮度）。status4値＝overdue/due_soon/pending/info。
D1（後ろ向き週次報告 summary_links）との差＝**前向きの会議準備＋WBS直近タスクの議題前出し**。
自由文生成（AI要約）はスコープ外。

## テスト（このマシン）
python -m pip install openpyxl pyyaml pytest
pytest tests/                 # 全緑＝該当ゲートまでのAC
- サンプル正本（01_PoC/議事録サンプル_…_v1.xlsx・WBSサンプル_…_v1.xlsx）は複製しない。
  conftest が parents[3]/01_PoC で解決（cwd非依存・MEETING_PREP_SAMPLES_DIR で上書き可）。
  CI は repo同梱 samples/ を MEETING_PREP_SAMPLES_DIR で参照する。
- e2eアンカー（specs §10・スポンサー独立再現一致 2026-06-14・一字一句この値で）conftest一元化:
  AS_OF="2026-07-10" / ASOF_WEEK="2026-W28" / HORIZON_DAYS=14 / MEETING_COUNT=6 /
  CARRYOVER overdue5・due_soon1・pending0・total6 / DECISION_FOLLOWUP=5 /
  WBS_TASK_COUNT=81 / UPCOMING_TASK=13 / ITEM_COUNT 焑21・有... 無11・有24。
- Windows/cp932。python -X utf8 で実行。

## 不変条件（specs §8 の写し）
1. Excel（議事録・WBS）は openpyxl(read_only=True)・書込禁止。出力は _output/ 別ファイル。
2. 全チェック項目に必ずセル参照（6キー・ref==render()）。手組み禁止。
3. 完了状態を推測しない（議事録に無い＝事実提示のみ・overdue_note 必須）。
4. WBS有無で carryover/decision_followup/freshness は不変（差は upcoming_task と related_phases のみ＝S-1）。
5. status語彙・horizon・stale_days・参照正規表現・書式は config 可変。封电10キーA1一致・ui_type="prep_checklist"。
6. 決定論（generated_at除き同一出力）。now()/today()禁止・deepcopy冪等。自由文生成なし。

## 決定論の要（事故りやすい）
- as_of＝既定 議事録の最新会議日（D1のmax方式とは別＝進捗報告を入力に取らないため）。
- status境界は閉区間: deadline<=as_of→overdue / as_of<deadline<=as_of+horizon→due_soon / それ以外→pending。
- 会議体は生表記・正規化しない。--meeting-type 指定時も upcoming_task は全件（会議体非依存・§15）。
- src/calendar.py を作らない（stdlib衰突。週ユーティリティは workcal.py）。

## アーキテクチャ / データフロー（ゲート順）
G1 model(D1複製) → G2 workcal(B1複製)+config(D1複製+D3固有) → G3 minutes_reader(D1複製)
→ G4 wbs_reader(C2複製+工程/開始/終了加算) → G5 prep core-A(carryover/decision/status/並び)
→ G6 prep core-B(upcoming_task/WBS突合/freshness/scope) → G7 envelope/renderer/cli+e2e+CI3本柱目
複製ファイルには複製元と確定IFの由来コメントを残す（スポンサー指示）。

## やってはいけないこと
- specs/meeting-prep.md を読まずに着手しない。CLIを介さず算出を自前再実装しない。
- 複製元（D1 model/minutes_reader・C2 wbs_reader既存部・B1 workcal）のロジックを改変しない（由来コメント・加算のみ）。
- サンプルExcelに書き込まない。封筒キー集合・evidence6キーをA1から逸らさない。
- 自由文を生成しない。完了状態を推測しない。会議体を正規化しない。
- スコープ外（AI生成／通知送信／未来日程管理／封筒チェーン入力／複数議事録統合／進捗報告取込／--project-type）に手を出さない。
