"""
Internationalization (i18n) for MySQL Data Factory 3.0.1 GUI.

Supports: zh_CN (简体中文), en (English), ja (日本語)
Language preference is persisted to config/gui_language.json.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_LANG_FILE = _PROJECT_ROOT / "config" / "gui_language.json"

# Current language code
_current_lang: str = "zh_CN"

# ─────────────────────────────────────────────
# Text resources
# Keys follow: <page>.<element> pattern
# ─────────────────────────────────────────────

_TEXTS: dict[str, dict[str, str]] = {
    # ── Window ──
    "window.title": {
        "zh_CN": "MySQL Data Factory 3.0.1",
        "en":    "MySQL Data Factory 3.0.1",
        "ja":    "MySQL Data Factory 3.0.1",
    },

    # ── Tab names ──
    "tab.connection": {"zh_CN": "1. 数据库连接", "en": "1. Connection", "ja": "1. DB接続"},
    "tab.scan":       {"zh_CN": "2. 数据库扫描", "en": "2. Scan",       "ja": "2. スキャン"},
    "tab.tasks":      {"zh_CN": "3. 任务配置",   "en": "3. Tasks",      "ja": "3. タスク設定"},
    "tab.preview":    {"zh_CN": "4. 预览确认",   "en": "4. Preview",    "ja": "4. プレビュー"},
    "tab.execute":    {"zh_CN": "5. 执行",       "en": "5. Execute",    "ja": "5. 実行"},
    "tab.history":    {"zh_CN": "6. 历史记录",   "en": "6. History",    "ja": "6. 履歴"},

    # ── Menu ──
    "menu.language":       {"zh_CN": "语言 / Language", "en": "Language", "ja": "言語"},
    "menu.lang_zh":        {"zh_CN": "简体中文",        "en": "简体中文", "ja": "簡体中国語"},
    "menu.lang_en":        {"zh_CN": "English",         "en": "English",  "ja": "English"},
    "menu.lang_ja":        {"zh_CN": "日本語",          "en": "日本語",   "ja": "日本語"},

    # ── Connection page ──
    "conn.profile_group":   {"zh_CN": "连接配置",     "en": "Connection Profile", "ja": "接続プロファイル"},
    "conn.profile_label":   {"zh_CN": "配置:",        "en": "Profile:",           "ja": "プロファイル:"},
    "conn.save_profile":    {"zh_CN": "保存配置",     "en": "Save Profile",       "ja": "プロファイル保存"},
    "conn.delete_profile":  {"zh_CN": "删除配置",     "en": "Delete Profile",     "ja": "プロファイル削除"},
    "conn.load_env":        {"zh_CN": "从 .env 加载", "en": "Load from .env",     "ja": ".envから読込"},
    "conn.settings_group":  {"zh_CN": "连接参数",     "en": "Connection Settings", "ja": "接続設定"},
    "conn.host":            {"zh_CN": "主机:",        "en": "Host:",              "ja": "ホスト:"},
    "conn.port":            {"zh_CN": "端口:",        "en": "Port:",              "ja": "ポート:"},
    "conn.user":            {"zh_CN": "用户名:",      "en": "User:",              "ja": "ユーザー:"},
    "conn.password":        {"zh_CN": "密码:",        "en": "Password:",          "ja": "パスワード:"},
    "conn.database":        {"zh_CN": "数据库:",      "en": "Database:",          "ja": "データベース:"},
    "conn.charset":         {"zh_CN": "字符集:",      "en": "Charset:",           "ja": "文字セット:"},
    "conn.test":            {"zh_CN": "测试连接",     "en": "Test Connection",    "ja": "接続テスト"},
    "conn.connect":         {"zh_CN": "连接并继续",   "en": "Connect & Continue", "ja": "接続して次へ"},
    "conn.disconnect":      {"zh_CN": "断开连接",     "en": "Disconnect",         "ja": "切断"},
    "conn.reconnect":       {"zh_CN": "重新连接",     "en": "Reconnect",          "ja": "再接続"},
    "conn.status_ok":       {"zh_CN": "连接成功 - {n} 张表", "en": "OK - {n} tables found", "ja": "接続成功 - {n} テーブル"},
    "conn.status_fail":     {"zh_CN": "连接失败",     "en": "Connection failed",  "ja": "接続失敗"},
    "conn.status_active":   {"zh_CN": "已连接: {info}", "en": "Connected: {info}", "ja": "接続中: {info}"},
    "conn.status_disconnected": {"zh_CN": "未连接", "en": "Disconnected", "ja": "未接続"},
    "conn.db_required":     {"zh_CN": "数据库名不能为空", "en": "Database name is required.", "ja": "データベース名は必須です"},
    "conn.connect_error":   {"zh_CN": "无法连接数据库", "en": "Cannot connect to database.", "ja": "データベースに接続できません"},
    "conn.loaded_env":      {"zh_CN": "已从 .env 加载", "en": "Loaded from .env", "ja": ".envから読込完了"},

    # ── Scan page ──
    "scan.btn_scan":        {"zh_CN": "扫描数据库",       "en": "Scan Database",       "ja": "データベーススキャン"},
    "scan.btn_load_cache":  {"zh_CN": "加载缓存结果",     "en": "Load Cached Scan",    "ja": "キャッシュ読込"},
    "scan.btn_use":         {"zh_CN": "使用此扫描结果",   "en": "Use This Scan Result","ja": "このスキャン結果を使用"},
    "scan.scanning":        {"zh_CN": "正在扫描...",       "en": "Scanning...",          "ja": "スキャン中..."},
    "scan.progress":        {"zh_CN": "扫描 {c}/{t}: {name}", "en": "Scanning {c}/{t}: {name}", "ja": "スキャン {c}/{t}: {name}"},
    "scan.complete":        {"zh_CN": "扫描完成: {n} 张表 ({time})", "en": "Scan complete: {n} tables ({time})", "ja": "スキャン完了: {n} テーブル ({time})"},
    "scan.error":           {"zh_CN": "扫描错误",         "en": "Scan Error",           "ja": "スキャンエラー"},
    "scan.no_cache":        {"zh_CN": "未找到缓存",       "en": "No Cache",             "ja": "キャッシュなし"},
    "scan.no_cache_msg":    {"zh_CN": "没有找到缓存的扫描结果", "en": "No cached scan results found.", "ja": "キャッシュされたスキャン結果が見つかりません"},
    "scan.loaded_cache":    {"zh_CN": "已加载缓存: {n} 张表 ({time})", "en": "Loaded cached scan: {n} tables ({time})", "ja": "キャッシュ読込: {n} テーブル ({time})"},
    "scan.col_table":       {"zh_CN": "表名",     "en": "Table Name",     "ja": "テーブル名"},
    "scan.col_rows":        {"zh_CN": "行数",     "en": "Rows",           "ja": "行数"},
    "scan.col_pk":          {"zh_CN": "主键",     "en": "PK Columns",     "ja": "主キー"},
    "scan.col_unique":      {"zh_CN": "唯一键",   "en": "Unique Columns", "ja": "ユニークキー"},
    "scan.col_json":        {"zh_CN": "JSON 列",  "en": "JSON Columns",   "ja": "JSON列"},
    "scan.col_time":        {"zh_CN": "时间字段", "en": "Time Columns",   "ja": "時間列"},
    "scan.col_marker":      {"zh_CN": "标识字段", "en": "Marker Columns", "ja": "マーカー列"},

    # ── Tasks page ──
    "tasks.add_tables":     {"zh_CN": "添加表",       "en": "Add Tables",      "ja": "テーブル追加"},
    "tasks.table_label":    {"zh_CN": "表:",           "en": "Table:",           "ja": "テーブル:"},
    "tasks.btn_add":        {"zh_CN": "添加",         "en": "Add Table",       "ja": "追加"},
    "tasks.btn_remove":     {"zh_CN": "移除选中",     "en": "Remove Selected", "ja": "選択削除"},
    "tasks.select_hint":    {"zh_CN": "选择表进行配置", "en": "Select a table to configure", "ja": "テーブルを選択して設定"},
    "tasks.confirm":        {"zh_CN": "确认并预览",   "en": "Confirm & Preview","ja": "確認してプレビュー"},
    "tasks.summary":        {"zh_CN": "{n} 张表, 约 {rows} 行", "en": "{n} tables, ~{rows} rows total", "ja": "{n} テーブル, 約 {rows} 行"},
    "tasks.no_tasks":       {"zh_CN": "请添加至少一张表", "en": "Add at least one table.", "ja": "テーブルを1つ以上追加してください"},
    "tasks.already_added":  {"zh_CN": "{name} 已在任务列表中", "en": "{name} is already in the task list.", "ja": "{name} はすでに追加されています"},
    "tasks.sample_method":  {"zh_CN": "样本方法:",   "en": "Sample Method:", "ja": "サンプル方法:"},
    "tasks.sample_pk":      {"zh_CN": "样本主键值:", "en": "Sample PK Value:", "ja": "サンプルPK値:"},
    "tasks.sample_where":   {"zh_CN": "WHERE 条件:", "en": "Sample WHERE:", "ja": "WHERE条件:"},
    "tasks.pk_mode":        {"zh_CN": "主键模式:",   "en": "PK Mode:", "ja": "PKモード:"},
    "tasks.pk_start":       {"zh_CN": "起始值:",     "en": "PK Start:", "ja": "開始値:"},
    "tasks.pk_end":         {"zh_CN": "结束值:",     "en": "PK End:", "ja": "終了値:"},
    "tasks.pk_prefix":      {"zh_CN": "主键前缀:",   "en": "PK Prefix:", "ja": "PKプレフィックス:"},
    "tasks.zero_pad":       {"zh_CN": "补零宽度:",   "en": "Zero Pad Width:", "ja": "ゼロ埋め幅:"},
    "tasks.row_count":      {"zh_CN": "生成行数:",   "en": "Row Count:", "ja": "生成行数:"},
    "tasks.batch_size":     {"zh_CN": "批次大小:",   "en": "Batch Size:", "ja": "バッチサイズ:"},
    "tasks.mode":           {"zh_CN": "执行模式:",   "en": "Mode:", "ja": "実行モード:"},
    "tasks.marker_col":     {"zh_CN": "标识字段:",   "en": "Marker Column:", "ja": "マーカー列:"},
    "tasks.marker_val":     {"zh_CN": "标识值:",     "en": "Marker Value:", "ja": "マーカー値:"},

    # ── Preview page ──
    "preview.no_plan":      {"zh_CN": "未加载计划", "en": "No plan loaded", "ja": "プランなし"},
    "preview.summary":      {"zh_CN": "Campaign: {cid} | 表: {tables} | 总行数: {rows}", "en": "Campaign: {cid} | Tables: {tables} | Total rows: {rows}", "ja": "Campaign: {cid} | テーブル: {tables} | 合計行数: {rows}"},
    "preview.refresh":      {"zh_CN": "刷新预览",   "en": "Refresh Preview", "ja": "プレビュー更新"},
    "preview.execute":      {"zh_CN": "执行 Campaign", "en": "Execute Campaign", "ja": "Campaign 実行"},
    "preview.first_rows":   {"zh_CN": "预览 (前 5 行):", "en": "Preview (first 5 rows):", "ja": "プレビュー (最初の5行):"},
    "preview.confirm_title":{"zh_CN": "确认执行", "en": "Confirm Execution", "ja": "実行確認"},
    "preview.confirm_msg":  {"zh_CN": "执行包含 {tables} 张表, 共 {rows} 行的 Campaign?\n\nCampaign ID: {cid}", "en": "Execute campaign with {tables} tables, {rows} total rows?\n\nCampaign ID: {cid}", "ja": "{tables} テーブル, 合計 {rows} 行の Campaign を実行しますか？\n\nCampaign ID: {cid}"},

    # ── Execute page ──
    "exec.no_exec":         {"zh_CN": "无正在执行的任务", "en": "No execution in progress", "ja": "実行中のタスクなし"},
    "exec.running":         {"zh_CN": "正在执行 Campaign: {cid}", "en": "Executing campaign: {cid}", "ja": "Campaign 実行中: {cid}"},
    "exec.progress":        {"zh_CN": "任务 {idx}/{total} - {phase}: {detail}", "en": "Task {idx}/{total} - {phase}: {detail}", "ja": "タスク {idx}/{total} - {phase}: {detail}"},
    "exec.detail_title":     {"zh_CN": "执行详情",   "en": "Execution Detail", "ja": "実行詳細"},
    "exec.results":         {"zh_CN": "任务结果",   "en": "Task Results",    "ja": "タスク結果"},
    "exec.log":             {"zh_CN": "执行日志",   "en": "Execution Log",   "ja": "実行ログ"},
    "exec.stop":            {"zh_CN": "停止",       "en": "Stop",            "ja": "停止"},
    "exec.complete":        {"zh_CN": "Campaign {cid}: {status}", "en": "Campaign {cid}: {status}", "ja": "Campaign {cid}: {status}"},
    "exec.status_ok":       {"zh_CN": "已完成",     "en": "COMPLETED",       "ja": "完了"},
    "exec.status_err":      {"zh_CN": "有错误完成", "en": "COMPLETED WITH ERRORS", "ja": "エラーあり完了"},
    "exec.col_table":       {"zh_CN": "表名",       "en": "Table",           "ja": "テーブル"},
    "exec.col_status":      {"zh_CN": "状态",       "en": "Status",          "ja": "ステータス"},
    "exec.col_attempted":   {"zh_CN": "计划行数",   "en": "Attempted",       "ja": "計画行数"},
    "exec.col_inserted":    {"zh_CN": "实际插入",   "en": "Inserted",        "ja": "実際挿入"},
    "exec.col_failed":      {"zh_CN": "失败批次",   "en": "Failed Batches",  "ja": "失敗バッチ"},
    "exec.col_pkrange":     {"zh_CN": "主键区间",   "en": "PK Range",        "ja": "PK範囲"},

    # ── History page ──
    "hist.plans_tab":       {"zh_CN": "执行计划",   "en": "Plans",           "ja": "実行プラン"},
    "hist.reports_tab":     {"zh_CN": "执行报告",   "en": "Reports",         "ja": "実行レポート"},
    "hist.cleanup_tab":     {"zh_CN": "Cleanup SQL", "en": "Cleanup SQL",    "ja": "Cleanup SQL"},
    "hist.detail":          {"zh_CN": "详细信息",   "en": "Details",         "ja": "詳細"},
    "hist.cleanup_ops":     {"zh_CN": "清理操作",   "en": "Cleanup Operations", "ja": "クリーンアップ操作"},
    "hist.campaign_id":     {"zh_CN": "Campaign ID:", "en": "Campaign ID:",  "ja": "Campaign ID:"},
    "hist.dry_run":         {"zh_CN": "试运行清理", "en": "Dry Run Cleanup", "ja": "ドライラン"},
    "hist.execute_cleanup": {"zh_CN": "执行清理",   "en": "Execute Cleanup", "ja": "クリーンアップ実行"},
    "hist.refresh":         {"zh_CN": "刷新全部",   "en": "Refresh All",     "ja": "全更新"},
    "hist.confirm_delete_title": {"zh_CN": "确认删除", "en": "Confirm Deletion", "ja": "削除確認"},
    "hist.confirm_delete_msg":   {"zh_CN": "将删除 Campaign {cid} 的数据。\n影响表数: {n}\n\n确定？", "en": "This will DELETE data for campaign {cid}.\nTables affected: {n}\n\nAre you sure?", "ja": "Campaign {cid} のデータを削除します。\n対象テーブル数: {n}\n\nよろしいですか？"},
    "hist.cleanup_done":    {"zh_CN": "[{mode}] {n} 张表已处理。\n影响行数: {rows}", "en": "[{mode}] {n} tables processed.\nRows affected: {rows}", "ja": "[{mode}] {n} テーブル処理完了。\n影響行数: {rows}"},
    "hist.no_campaign":     {"zh_CN": "请输入 Campaign ID", "en": "Enter a campaign ID.", "ja": "Campaign IDを入力してください"},
    "hist.no_sql":          {"zh_CN": "未找到该 Campaign 的 Cleanup SQL", "en": "No cleanup SQL found for {cid}", "ja": "Campaign {cid} の Cleanup SQL が見つかりません"},
    "hist.no_targets":      {"zh_CN": "报告中未找到清理目标", "en": "No cleanup targets found in reports.", "ja": "レポートにクリーンアップ対象が見つかりません"},
    "hist.no_conn":         {"zh_CN": "未连接数据库，请先连接", "en": "No database connection. Go to Connection tab first.", "ja": "DB未接続。接続タブで先に接続してください"},
    "hist.col_time":        {"zh_CN": "时间",       "en": "Time",            "ja": "時間"},
    "hist.col_db":          {"zh_CN": "数据库",     "en": "Database",        "ja": "データベース"},
    "hist.col_table":       {"zh_CN": "表名",       "en": "Table",           "ja": "テーブル"},
    "hist.col_mode":        {"zh_CN": "模式",       "en": "Mode",            "ja": "モード"},
    "hist.col_rows":        {"zh_CN": "行数",       "en": "Rows",            "ja": "行数"},
    "hist.col_pk_col":      {"zh_CN": "主键字段",   "en": "PK Column",       "ja": "PKカラム"},
    "hist.col_pk_start":    {"zh_CN": "主键起始",   "en": "PK Start",        "ja": "PK開始"},
    "hist.col_pk_end":      {"zh_CN": "主键结束",   "en": "PK End",          "ja": "PK終了"},
    "hist.col_campaign":    {"zh_CN": "Campaign ID", "en": "Campaign ID",    "ja": "Campaign ID"},
    "hist.col_report":      {"zh_CN": "报告文件",   "en": "Report File",     "ja": "レポートファイル"},
    "hist.col_cleanup":     {"zh_CN": "Cleanup SQL", "en": "Cleanup SQL",    "ja": "Cleanup SQL"},
    "hist.col_status":      {"zh_CN": "状态",       "en": "Status",          "ja": "ステータス"},
    "hist.col_summary":     {"zh_CN": "摘要",       "en": "Summary",         "ja": "サマリー"},

    # ── Cleanup confirm dialog ──
    "hist.confirm_dialog_title":  {"zh_CN": "[!!] 删除确认 — 请仔细核对", "en": "[!!] Delete Confirmation", "ja": "[!!] 削除確認"},
    "hist.confirm_warning":       {"zh_CN": "警告：以下操作将从数据库中永久删除数据，不可恢复！请确认所有信息无误后再执行。",
                                   "en":    "WARNING: This will permanently DELETE data from the database. This cannot be undone. Please verify all details before confirming.",
                                   "ja":    "警告：以下の操作はデータベースからデータを完全に削除します。元に戻すことはできません。すべての情報を確認してから実行してください。"},
    "hist.confirm_info_group":    {"zh_CN": "清理目标信息",   "en": "Cleanup Target Info",   "ja": "クリーンアップ対象情報"},
    "hist.confirm_db":            {"zh_CN": "目标数据库:",    "en": "Database:",             "ja": "対象データベース:"},
    "hist.confirm_table":         {"zh_CN": "目标表:",        "en": "Table:",                "ja": "対象テーブル:"},
    "hist.confirm_campaign":      {"zh_CN": "Campaign ID:",  "en": "Campaign ID:",          "ja": "Campaign ID:"},
    "hist.confirm_pk_col":        {"zh_CN": "主键字段:",      "en": "PK Column:",            "ja": "PKカラム:"},
    "hist.confirm_pk_start":      {"zh_CN": "主键起始值:",    "en": "PK Start:",             "ja": "PK開始値:"},
    "hist.confirm_pk_end":        {"zh_CN": "主键结束值:",    "en": "PK End:",               "ja": "PK終了値:"},
    "hist.confirm_tables_count":  {"zh_CN": "涉及表数量:",    "en": "Tables:",               "ja": "対象テーブル数:"},
    "hist.confirm_total_rows":    {"zh_CN": "预计总删除行数:", "en": "Total Estimated Rows:",  "ja": "合計削除予定行数:"},
    "hist.confirm_est_rows":      {"zh_CN": "预计删除行数:",  "en": "Estimated Rows:",       "ja": "削除予定行数:"},
    "hist.confirm_sample_group":  {"zh_CN": "待删除数据样本（前5条）", "en": "Sample rows to be deleted (first 5)", "ja": "削除対象サンプル（先頭5件）"},
    "hist.confirm_no_sample":     {"zh_CN": "无法获取样本数据", "en": "Could not fetch sample rows.", "ja": "サンプルデータを取得できません"},
    "hist.confirm_delete_btn":    {"zh_CN": "确认删除这批测试数据", "en": "Confirm Delete This Test Data", "ja": "このテストデータを削除する"},
    "hist.confirm_cancel_btn":    {"zh_CN": "取消",           "en": "Cancel",               "ja": "キャンセル"},

    # ── Tasks page — template ──
    "tasks.btn_save_tpl":   {"zh_CN": "保存模板",   "en": "Save Template",   "ja": "テンプレート保存"},
    "tasks.btn_load_tpl":   {"zh_CN": "载入模板",   "en": "Load Template",   "ja": "テンプレート読込"},
    "tasks.btn_delete_tpl": {"zh_CN": "删除模板",   "en": "Delete Template", "ja": "テンプレート削除"},
    "tasks.tpl_group":      {"zh_CN": "任务模板",   "en": "Task Templates",  "ja": "タスクテンプレート"},
    "tasks.tpl_label":      {"zh_CN": "模板:",       "en": "Template:",       "ja": "テンプレート:"},
    "tasks.tpl_save_title": {"zh_CN": "保存任务模板", "en": "Save Task Template", "ja": "タスクテンプレート保存"},
    "tasks.tpl_save_prompt":{"zh_CN": "请输入模板名称:", "en": "Enter template name:", "ja": "テンプレート名を入力:"},
    "tasks.tpl_saved":      {"zh_CN": "模板已保存: {name}", "en": "Template saved: {name}", "ja": "テンプレート保存完了: {name}"},
    "tasks.tpl_loaded":     {"zh_CN": "模板已载入: {name} ({n} 张表)", "en": "Template loaded: {name} ({n} tables)", "ja": "テンプレート読込完了: {name} ({n} テーブル)"},
    "tasks.tpl_deleted":    {"zh_CN": "模板已删除: {name}", "en": "Template deleted: {name}", "ja": "テンプレート削除完了: {name}"},
    "tasks.tpl_no_tasks":   {"zh_CN": "当前无任务可保存", "en": "No tasks to save.", "ja": "保存するタスクがありません"},
    "tasks.tpl_no_select":  {"zh_CN": "请先选择模板", "en": "Select a template first.", "ja": "テンプレートを選択してください"},
    "tasks.tpl_confirm_del":{"zh_CN": "确认删除模板 \"{name}\" ?", "en": "Delete template \"{name}\"?", "ja": "テンプレート \"{name}\" を削除しますか？"},
    "tasks.tpl_load_err":   {"zh_CN": "载入模板失败: {err}", "en": "Failed to load template: {err}", "ja": "テンプレート読込失敗: {err}"},
    "tasks.tpl_table_skip": {"zh_CN": "跳过不在扫描结果中的表: {name}", "en": "Skipped table not in scan: {name}", "ja": "スキャン結果にないテーブルをスキップ: {name}"},

    # ── Conflict check ──
    "conflict.title":       {"zh_CN": "主键冲突检查", "en": "PK Conflict Check", "ja": "PK衝突チェック"},
    "conflict.checking":    {"zh_CN": "正在检查主键冲突...", "en": "Checking PK conflicts...", "ja": "PK衝突をチェック中..."},
    "conflict.no_conflict": {"zh_CN": "所有表主键范围无冲突，可以安全执行。", "en": "No PK conflicts found. Safe to proceed.", "ja": "PK衝突なし。安全に実行できます。"},
    "conflict.found":       {"zh_CN": "发现主键冲突！", "en": "PK Conflicts Found!", "ja": "PK衝突が見つかりました！"},
    "conflict.table_hdr":   {"zh_CN": "表: {table}  |  主键: {pk}  |  冲突数: {n}", "en": "Table: {table}  |  PK: {pk}  |  Conflicts: {n}", "ja": "テーブル: {table}  |  PK: {pk}  |  衝突数: {n}"},
    "conflict.range_info":  {"zh_CN": "计划插入范围: {start} ~ {end}", "en": "Planned range: {start} ~ {end}", "ja": "挿入予定範囲: {start} ~ {end}"},
    "conflict.samples":     {"zh_CN": "冲突示例: {vals}", "en": "Conflict samples: {vals}", "ja": "衝突サンプル: {vals}"},
    "conflict.ask_continue":{"zh_CN": "\n是否忽略冲突继续执行？（不推荐）", "en": "\nIgnore conflicts and continue? (Not recommended)", "ja": "\n衝突を無視して続行しますか？（非推奨）"},
    "conflict.abort":       {"zh_CN": "已取消执行", "en": "Execution cancelled", "ja": "実行をキャンセルしました"},

    # ── Common ──
    "common.error":         {"zh_CN": "错误",       "en": "Error",           "ja": "エラー"},
    "common.info":          {"zh_CN": "信息",       "en": "Info",            "ja": "情報"},
    "common.warning":       {"zh_CN": "警告",       "en": "Warning",         "ja": "警告"},
    "common.ready":         {"zh_CN": "就绪",       "en": "Ready",           "ja": "準備完了"},
    "common.none":          {"zh_CN": "(无)",        "en": "(none)",          "ja": "(なし)"},
}


# ─────────────────────────────────────────────
# API
# ─────────────────────────────────────────────

def t(key: str, **kwargs) -> str:
    """Get translated text for current language. Supports {name} formatting."""
    entry = _TEXTS.get(key)
    if entry is None:
        return key  # fallback: return key itself
    text = entry.get(_current_lang, entry.get("en", key))
    if kwargs:
        try:
            text = text.format(**kwargs)
        except (KeyError, IndexError):
            pass
    return text


def get_lang() -> str:
    return _current_lang


def set_lang(lang: str) -> None:
    global _current_lang
    if lang in ("zh_CN", "en", "ja"):
        _current_lang = lang
        _save_lang(lang)


def load_saved_lang() -> None:
    """Load persisted language preference."""
    global _current_lang
    try:
        if _LANG_FILE.exists():
            with _LANG_FILE.open("r", encoding="utf-8") as f:
                data = json.load(f)
            lang = data.get("language", "zh_CN")
            if lang in ("zh_CN", "en", "ja"):
                _current_lang = lang
    except Exception:
        pass


def _save_lang(lang: str) -> None:
    """Persist language preference."""
    try:
        _LANG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with _LANG_FILE.open("w", encoding="utf-8") as f:
            json.dump({"language": lang}, f)
    except Exception:
        pass


# Load on import
load_saved_lang()








