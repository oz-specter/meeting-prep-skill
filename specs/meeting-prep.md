<!--
D3 meeting-prep-skill 仕様書（spec固定ドラフト・関所１審査対象）
起案: Cowork側PM 2026-06-14 ／ 論点表: 02_Skill/handoff/2026-06-14_D3論点表.md（★4点=全PM推奨で決定済）
複製元: D1 report-skill（minutes_reader/model/config md系・workcal）＋C2 risk-response-skill（wbs_reader）
-->

# 仕様書: D3 会議事前準備スキル（ui_type=prep_checklist）

## 1. 目的・背景

議事録(.xlsx)＋任意WBS(.xlsx)から、**次の会議までに片付ける／次の議題に載せるべき事項**を決定論でチェックリスト化し、A1互換エンベロープ（`ui_type=prep_checklist`・**確定UI型9種目**）で出す。

D1 report-skill（`summary_links`）が「過去を振り返りステークホルダーに伝える」**後ろ向きの週次報告**であるのに対し、D3 は「次の会議に向けて何を準備・確認するか」の**前向きのチェックリスト**である。同じ議事録を読むが、D3はさらに**WBSの直近着手/期限タスクを議題候補として前出しする**点がD1にない核（§4）。AIの自由文生成は行わず、テンプレ＋実測値のみ（concept/16 報告契約レイヤー）。

詳細はリポジトリ同梱の specs/meeting-prep.md を正本とする（チャット貼付けでなくファイル配置）。

> 注: 本README追記はスペース都合で要約版。完全版はリポジトリの specs/meeting-prep.md を参照。
