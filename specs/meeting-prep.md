<!--
D3 meeting-prep-skill 仕様書（spec固定・関所１承認済）
起案: Cowork側PM 2026-06-14 ／ 論点表: 02_Skill/handoff/2026-06-14_D3論点表.md（★4点=全PM推奨で決定済）
複製元: D1 report-skill（minutes_reader/model/config md系・workcal）＋C2 risk-response-skill（wbs_reader）
-->

# 仕様書: D3 会議事前準備スキル（ui_type=prep_checklist）

## 1. 目的・背景

議事録(.xlsx)＋任意WBS(.xlsx)から、**次の会議までに片付ける／次の議題に載せるべき事項**を決定論でチェックリスト化し、A1互換エンベロープ（`ui_type=prep_checklist`・**確定UI型9種目**）で出す。

D1 report-skill（`summary_links`）が「過去を振り返りステークホルダーに伝える」**後ろ向きの週次報告**であるのに対し、D3 は「次の会議に向けて何を準備・確認するか」の**前向きのチェックリスト**である。同じ議事録を読むが、D3はさらに**WBSの直近着手/期限タスクを議題候補として前出しする**点がD1にない核（§4）。AIの自由文生成は行わず、テンプレ＋実測値のみ（concept/16 報告契約レイヤー）。

## 2. 入力と前提

- **議事録（必須）**: シート"議事録"。必須列 `["日付","会議体","決定事項"]`、任意列 `["出席","宿題_内容","宿題_担当","宿題_期限","関連タスク","関連要件"]`（D1 `minutes_reader` 逐語複製・改変なし）。
- **WBS（任意・`--wbs`）**: シート"WBS"。最小ビュー必須列 `["タスクID","タスク名"]`、別名対応列 `担当/開始日/終了日`、加えてD3で `工程` を加算読み（C2 `wbs_reader` 複製＋加算）。
- 必須入力の列/シート欠落は `MissingColumnReport` → 非envelope=exit2／envelope=`status=degraded`・exit0（全スキル共通規約）。
- 決定論: 同一入力＝同一出力。`now()`/`today()` 禁止（ファイル名スタンプと `generated_at` のみ可）。

### 2.1 as_of 規約と horizon（D1/C3対称設計の継承・論点#5）

- `--as-of YYYY-MM-DD` 任意・**既定 = 議事録の最新会議日**（データ由来）。`as_of_week` は ISO週（B1 `workcal` 複製）。
- `--horizon-days` 任意・既定 **14**。due_soon 窓は**閉区間** `[as_of, as_of + horizon_days]`。
- 議事録が古い（最終会議日からの days_since > `stale_days`=30）場合は `freshness` 項目＋`notice.stale_minutes` に出る（D1対称）。

## 3. 生成モデル（4区分 → status付与・★#2）

### 3.1 区分表（すべて config 可変）

| 区分 kind | 源 | 生成条件（決定論） |
|---|---|---|
| `carryover_action` | 議事録 | `宿題_内容` が非空の各宿題（完了状態は議事録に無い＝全件を未消込として載せる・★#4） |
| `decision_followup` | 議事録 | `決定事項` に `RK-\d+` または `R-\d+` 参照を含む決定（config 正規表現） |
| `upcoming_task` | WBS | `--wbs` 指定時のみ。`開始日` または `終了日` が due_soon 窓 `[as_of, as_of+horizon]` に入るWBSタスク |
| `freshness` | 議事録 | 最終会議日からの days_since > `stale_days`（30） |

### 3.2 status 分岐（決定論・固定4値・閉区間）

`carryover_action` の status は `宿題_期限` で分岐:
- `deadline <= as_of` → **`overdue`**（as_of 当日は overdue 側に含む）
- `as_of < deadline <= as_of + horizon` → **`due_soon`**
- それ以外（窓より後）または期限なし → **`pending`**

`upcoming_task` = `due_soon`（窓内定義のため）。`decision_followup` = `pending`。`freshness` = `info`。
status 日本語ラベル（`期限経過/期限間近/未確認/参考`）は config 可変・識別子は機械判別用に固定。

### 3.3 並び順（決定論）

status 優先（`overdue`→`due_soon`→`pending`→`info`）→ 期日昇順（期日なしは末尾）→ 入力出現順（議事録行→WBS行）。安定ソートで入力行順に依存しない（B節 S-5）。

## 4. 議事録×WBS の突合（任意 `--wbs`・★#3）

- 議事録 `関連タスク`（`T05a` 等）→ WBS `タスクID` を決定論突合（C2 `wbs_reader` 座標台帳・名称ヒューリスティック突合は採らない）。
- **`upcoming_task` 区分の生成そのものがWBS由来**（C3のenrichment専用と異なる点）。さらに `carryover_action`/`decision_followup` の各項目に、紐づくタスクの `related_phases`（工程）と期日根拠を enrichment。
- WBS有無で `carryover_action`/`decision_followup`/`freshness` の3区分は**完全一致**（差は `upcoming_task` の有無と `related_phases` のみ）＝B節 S-1。
- 未知タスクID・`工程`列欠落は `notice.unknown_tasks`／警告＋当該enrichmentなし続行（クラッシュ禁止・B1/C3同型）。

## 5. 出力（payload）

```
payload = {
  "as_of": "YYYY-MM-DD", "as_of_week": "YYYY-Www", "horizon_days": 14,
  "meeting_scope": "<会議体> | all",
  "headline": "<config書式の決定論文>",
  "checklist": [
    {kind, status, title, owner, due("YYYY-MM-DD"|""), related_tasks[],
     related_phases[](--wbs時のみ), evidence[6キーCellRef...]}
  ],
  "summary": {item_count, by_status:{overdue,due_soon,pending,info}, by_kind:{...}},
  "overdue_note": "※完了状態は議事録に記録がありません（期限経過は事実の提示のみ）",
  "recommended_actions": [...]
}
```

- 封筒トップレベル10キーA1一致・`skill_id="meeting-prep-skill"`・evidence6キー固定（`sheet/column/row/value/note/ref`）・`ref == CellRef.render()`（ENVELOPE_STANDARD準拠）。
- `meta = {project_name, project_type(=None), item_count, overdue_count, due_soon_count, as_of, as_of_week, unit:"件"}`（加算的）。

### 5.1 recommended_actions（決定論・固定順・論点#14）

(1) overdue>0 → 「期限経過の宿題 {n}件の状況を次回会議で確認」 (2) upcoming_task>0 → 「{horizon}日以内に着手/期限の {n}タスクを議題化」 (3) decision_followup>0 → 「決定に紐づくリスク/要件 {n}件の進捗を確認」 (4) freshness発火 → 「議事録が {days}日更新なし・最新化を依頼」。全０件時は `[]`。

## 6. エンベロープ（A1スキーマ互換）

D1/C3 `envelope.py` 同型。`build_envelope(checklist_result, *, title, project_name, status, notice)` と `from_missing_report(report, ...)`（degraded）。`generated_at = now().isoformat(timespec="seconds")`（出力スタンプ専用・payload/metaには時刻を入れない）。

## 7. CLI と出力フォーマット

```
python src/cli.py --minutes <議事録.xlsx> [--wbs <WBS.xlsx>]
                  --out _output/ --format md|html|json|csv|envelope
                  [--project-name 名] [--as-of YYYY-MM-DD] [--horizon-days 14]
                  [--meeting-type 会議体] [--stale-days 30]
```

- 出力 `_output/会議準備チェックリスト_YYYYMMDD_HHMMSS.<ext>`（秒粒度・envelopeは`.envelope.json`）・`history.jsonl` 追記。
- `--meeting-type` 指定時は当該会議体に紐づく項目のみ／未指定時は全会議体横断（未指定＝上位集合・B節 S-4）。ただし upcoming_task は scope非依存全件（§15）。
- **CSV契約**: 1チェック項目=1行 tidy・UTF-8 BOM（**BOM付与は cli 責務**）・日本語固定9列 `プロジェクト, 区分, 状態, 項目, 担当, 期日, 関連タスク, 関連工程, 根拠セル参照(';'連結)`。項目0件は header 1行のみ exit0。
- `--project-name` 正準名の明示渡しを SKILL.md で必須運用に（ENVELOPE_STANDARD補足）。exit規約は全スキル共通（0=正常/2=必須列欠落/その他=異常）。

## 8. 不変条件（譲らないライン）

1. 決定論（`now()`/`today()` 非依存・同一入力同一出力）。
2. 完了状態を**推測しない**（議事録に無い＝事実提示のみ・`overdue_note` 必須・★#4）。
3. WBS有無で判定区分3種は不変（差は `upcoming_task` と enrichment のみ・S-1）。
4. evidence は全項目で CellRef 由来（手組み禁止・`ref==render()`）。
5. 自由文生成なし（テンプレ＋実測値・concept/16）。
6. 複製元（D1 minutes_reader/model・C2 wbs_reader の既存部・B1 workcal）の振る舞いは改変しない（由来コメント・加算のみ）。

## 9. Acceptance Criteria（pytest tests/ で機械検証）

- **AC-1**: 議事録readerはD1逐語複製で同一抽出（MeetingEntry の全フィールド一致・座標台帳CellRef一致）。
- **AC-2**: WBS readerはC2複製＋`工程`/`開始日`/`終了日` 加算読み（C2部の挙動不変・既存テスト緑）。
- **AC-3**: `carryover_action` を宿題非空の全件生成（サンプル6件・★#4）。
- **AC-4**: status 境界（§3.2）— `deadline==as_of`→overdue、`deadline==as_of+horizon`→due_soon、窓外→pending（閉区間・S-2）。
- **AC-5**: `decision_followup` を `RK-\d+`/`R-\d+` 参照を含む決定のみ生成（config正規表現・サンプル5件）。
- **AC-6**: `--wbs` 指定時のみ `upcoming_task` 生成（窓内に開始or終了のタスク）。
- **AC-7**: WBS有/無で carryover/decision_followup/freshness 完全一致・item_count差=upcoming_task件数（S-1）。
- **AC-8**: 並び順 status→期日→出現順、安定ソート（入力行入替で出力不変・S-5）。
- **AC-9**: `freshness` は days_since>stale_days で発火・既定as_of（最新会議日）では不発火、`--as-of` 後ろ倒しで発火（S-6）。
- **AC-10**: payload 契約（§5キー）・evidence6キー・`ref==CellRef.render()`。
- **AC-11**: 封筒トップレベル10キーA1一致・`skill_id`・meta加算キー。
- **AC-12**: recommended_actions 決定論固定順（§5.1）・全０件で `[]`。
- **AC-13**: notice 契約（§10）・非空フィールドのみ・全空null。
- **AC-14**: degraded（必須列欠落）= `from_missing_report` → status=degraded・exit0（envelope）／exit2（非envelope）。
- **AC-15**: CSV 9列・1項目1行・BOMはcli・項目0件はheader1行exit0。
- **AC-16**: md/html/json/csv/envelope 各format生成（D1/C3同型・level/status・evidence ref含む）。
- **AC-17**: `--meeting-type` スコープ（指定=部分集合・未指定=全件・S-4）。
- **AC-18**: deepcopy冪等（同一入力で2回実行＝完全一致・入力非破壊）。
- **AC-19**: `unknown_tasks`（議事録関連タスクがWBS未存在）を notice に記録し突合スキップ続行（クラッシュなし）。
- **AC-20**: e2eアンカー（§10）を conftest 凍結値と照合（独立再現一致）。

## 10. e2eアンカー表（PM実測 2026-06-14・関所１固定条件＝スポンサー独立再現で凍結）

入力: `01_PoC/議事録サンプル_人事給与SaaS導入_v1.xlsx`（6会議）＋`01_PoC/WBSサンプル_人事給与SaaS導入_v1.xlsx`（81タスク）・既定 horizon=14。

| # | アンカー | PM実測値 |
|---|---|---|
| A-1 | `as_of`（議事録最新会議日） | **2026-07-10** |
| A-2 | `as_of_week` | **2026-W28** |
| A-3 | due_soon 窓 | **2026-07-10 〜 2026-07-24** |
| A-4 | `carryover_action` 内訳 | overdue **5** / due_soon **1** / pending **0**（計6） |
| A-5 | `decision_followup` 件数 | **5**（R-01〜R-10含む決定・RK-05/RK-02/RK-01/RK-12/RK-09 参照） |
| A-6 | `upcoming_task` 件数（`--wbs`時・窓内に開始or終了） | **13** / 81 |
| A-7 | `freshness` 発火 | **不発火**（last_meeting=as_of・days_since=0） |
| A-8 | `item_count`（WBS無） | **11**（carryover6＋decision5＋freshness0） |
| A-9 | `item_count`（WBS有） | **24**（11＋upcoming13）＝S-1差分 **13** |

※凍結手順: 上表をPM実測として提示。スポンサー（または独立実行）が同サンプルで再現し一致を確認後、conftest に一元凍結（テストでハードコードせず conftest 参照）。値が割れたら spec を再確認（B1/D1/C3新標準①）。

## 11. 実装方針（src/構成・論点#7）

| ファイル | 由来 | 備考 |
|---|---|---|
| `src/model.py` | D1複製（CellRef/SheetView/MissingColumnReport/MeetingEntry/MinutesRegister） | 改変禁止・由来コメント |
| `src/minutes_reader.py` | D1複製（議事録reader・座標台帳） | 改変禁止 |
| `src/workcal.py` | B1複製（ISO週） | 改変禁止 |
| `src/wbs_reader.py` | C2複製＋`工程`/`開始日`/`終了日` 読み | 加算的（C2部不変） |
| `src/config.py` | D1複製＋D3固有（status語彙・horizon・区分書式・参照正規表現＝論点#11） | D1部改変禁止 |
| `src/prep.py` | **新規コア**（4区分枚挙→status付与→WBS突合enrich→並び） | deepcopy冪等・now()禁止 |
| `src/envelope.py`／`src/renderer.py`／`src/cli.py`／`SKILL.md` | 新規（D1/C3同型） | — |

`src/calendar.py` は作らない（stdlib衰突）。封筒チェーン入力は採らない（D1/C3前例）。進捗報告は取り込まない（D3は議事録＋WBSのみ）。

## 12. スコープ外（論点#16の転記・関所１固定条件）

自由文生成（議題文・要約のAI生成）／会議招集・通知送信（カレンダー/メール連携）／未来会議日程の管理・スケジューリング／封筒チェーン入力／複数議事録・複数WBSの統合／宿題の完了状態推定（★#4）／進捗報告の取り込み（D1/B1の領分）／`--project-type`／D1・C2 既存スキルの config・挙動変更。

## 13. 検証手順

1. `pytest`（AC-1〜AC-20）。`EXPECTED_PASSED` はゲートPR内で確定リファレンス更新。
2. CLI実走（5format×WBS有無）でクラッシュなし・exit規約・CSV列数。
3. e2eアンカー（§10）をスポンサー独立再現で照合し conftest 凍結。
4. CI 2本柱（pytest照合＋sha256マニフェスト）→ 境界再現スクリプト（3本柱目）はCLI完成ゲートで追加（C3前例）。

## 14. 想定リスク・確認事項（関所１での確認点）

- **D1との重複懸念**: carryover/decision は議事録由来でD1の actions/decisions と源が同じ。差別化は「前向きチェックリスト＋WBS議題前出し＋status消込前提」。§4 upcoming_task がD3固有価値であることを関所１で合意。
- **`meeting_scope` の紐付け**: §15で確定（scope指定時も upcoming_task は全件）。
- **horizon 既定14日**: 週次〜隔週会議を想定。現場の会議頻度で見直す暗定標準。
- アンカー A-5/A-6 はサンプル実測。スポンサー独立再現で割れたら正規表現・窓境界の解釈を再確認。

---

## 15. 関所１ 確定事項（2026-06-14・スポンサー承認）

- **spec固定承認**: 本仕様書をこの内容で固定（関所１通過）。論点表★4点＝全PM推奨で決定済。
- **§14残り1点の決定**: `--meeting-type` でスコープを絞った場合も **`upcoming_task` は全件含める**（WBS期日由来＝会議体非依存・議題候補として有用）。`carryover_action`/`decision_followup` のみ会議体一致でフィルタする。→ §3.1/§4/B節S-4 はこの解釈で実装する。
- 次工程: e2eアンカー（§10）独立再現で凍結 → report-skill雛形から `meeting-prep-skill` private repo 初期化 → ゲート分割案（別handoff）→ 1ゲート=1PR。
