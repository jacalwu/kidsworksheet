"""
管理員模組：提供管理員功能，包含查看使用者、調整配額、匯出 CSV 等。
"""

import csv
import io
from datetime import datetime, timezone
from typing import Optional

import streamlit as st

from utils.database import (
    get_all_users,
    get_all_usage_records,
    get_user_by_id,
    update_user_credits,
    get_connection,
    get_all_settings,
    set_setting,
    delete_setting,
)


def render_admin_panel(config: dict = None) -> None:
    """繪製管理員控制面板"""
    st.markdown("## 🛠️ 管理員控制台")

    if not st.session_state.get("is_admin"):
        st.error("❌ 您沒有管理員權限。")
        return

    # 分頁
    tab1, tab2, tab3, tab4, tab5 = st.tabs([
        "👥 使用者管理", "📊 使用紀錄", "📥 匯出資料", "⚙️ LLM 配置", "🔐 OAuth 整合",
    ])

    with tab1:
        _render_user_management()

    with tab2:
        _render_usage_records()

    with tab3:
        _render_export()

    with tab4:
        _render_llm_config(config or {})

    with tab5:
        _render_oauth_config(config or {})


def _render_user_management() -> None:
    """繪製使用者管理頁面"""
    st.markdown("### 👥 使用者列表")

    users = get_all_users()

    if not users:
        st.info("尚無使用者資料。")
        return

    # 統計資訊
    total_users = len(users)
    total_admins = sum(1 for u in users if u["is_admin"])
    total_credits = sum(u["credits"] for u in users)

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("總使用者數", total_users)
    with col2:
        st.metric("管理員數", total_admins)
    with col3:
        st.metric("總剩餘配額", total_credits)

    st.markdown("---")

    # 使用者表格
    for user in users:
        with st.expander(
            f"{'👑 ' if user['is_admin'] else '👤 '} {user['username']} "
            f"｜剩餘配額：{user['credits']}｜"
            f"註冊時間：{user['created_at'][:10] if user['created_at'] else 'N/A'}"
        ):
            col_a, col_b = st.columns([2, 1])

            with col_a:
                st.markdown(f"**使用者 ID**：{user['id']}")
                st.markdown(f"**電子郵件**：{user['email'] or '未提供'}")
                oauth = user.get("oauth_provider") or "本地帳號"
                st.markdown(f"**登入方式**：{oauth}")

                # 該使用者的使用統計
                conn = get_connection()
                usage_count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM usage_records WHERE user_id = ?",
                    (user["id"],),
                ).fetchone()["cnt"]
                kids_count = conn.execute(
                    "SELECT COUNT(*) as cnt FROM kids WHERE user_id = ?",
                    (user["id"],),
                ).fetchone()["cnt"]
                conn.close()

                st.markdown(f"**Kid 數量**：{kids_count}")
                st.markdown(f"**累計使用次數**：{usage_count}")

            with col_b:
                # 調整配額
                new_credits = st.number_input(
                    "調整配額",
                    min_value=0,
                    max_value=999999,
                    value=user["credits"],
                    key=f"credits_{user['id']}",
                )
                if st.button("💾 儲存配額", key=f"save_{user['id']}"):
                    if new_credits != user["credits"]:
                        update_user_credits(user["id"], new_credits)
                        st.success(f"已更新 {user['username']} 的配額：{user['credits']} → {new_credits}")
                        st.rerun()
                    else:
                        st.info("配額未變更。")


def _render_usage_records() -> None:
    """繪製使用紀錄頁面"""
    st.markdown("### 📊 使用紀錄")

    records = get_all_usage_records()

    if not records:
        st.info("尚無使用紀錄。")
        return

    # 篩選選項
    col_f1, col_f2 = st.columns(2)
    with col_f1:
        filter_type = st.selectbox(
            "依類型篩選",
            ["全部", "worksheet", "exam"],
            key="admin_filter_type",
        )
    with col_f2:
        # 取得所有使用者名稱作為篩選
        users = get_all_users()
        user_options = ["全部"] + [u["username"] for u in users]
        filter_user = st.selectbox(
            "依使用者篩選",
            user_options,
            key="admin_filter_user",
        )

    # 套用篩選
    filtered = records
    if filter_type != "全部":
        filtered = [r for r in filtered if r["type"] == filter_type]
    if filter_user != "全部":
        filtered = [r for r in filtered if r["username"] == filter_user]

    st.markdown(f"共 {len(filtered)} 筆紀錄（總計 {len(records)} 筆）")

    # 表格顯示
    if filtered:
        table_data = []
        for r in filtered[:200]:  # 限制顯示 200 筆
            table_data.append({
                "ID": r["id"],
                "使用者": r["username"],
                "類型": "📝 練習題" if r["type"] == "worksheet" else "📋 考試卷",
                "檔案": r["file_name"] or "-",
                "扣點": r["credits_used"],
                "時間": r["created_at"][:19] if r["created_at"] else "-",
            })

        st.dataframe(
            table_data,
            use_container_width=True,
            hide_index=True,
        )

        if len(records) > 200:
            st.caption(f"（僅顯示前 200 筆，共 {len(records)} 筆）")


def _render_export() -> None:
    """繪製資料匯出頁面"""
    st.markdown("### 📥 匯出資料")

    col1, col2 = st.columns(2)

    with col1:
        if st.button("📊 匯出使用者資料（CSV）", use_container_width=True):
            csv_data = _export_users_csv()
            st.download_button(
                label="⬇️ 下載使用者資料 CSV",
                data=csv_data,
                file_name=f"users_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )

    with col2:
        if st.button("📋 匯出使用紀錄（CSV）", use_container_width=True):
            csv_data = _export_usage_csv()
            st.download_button(
                label="⬇️ 下載使用紀錄 CSV",
                data=csv_data,
                file_name=f"usage_records_{datetime.now().strftime('%Y%m%d_%H%M')}.csv",
                mime="text/csv",
            )


def _render_llm_config(config: dict) -> None:
    """繪製 LLM 配置頁面，讓管理員在 UI 中修改 LLM 與 Web Search 參數

    所有修改會直接寫入資料庫（app_settings 表），
    優先於 config.toml / secrets / 環境變數。
    """
    st.markdown("### ⚙️ LLM 與搜尋引擎配置")
    st.caption(
        "在此修改的設定會儲存到資料庫，優先於 `config.toml` 與 `secrets.toml`。"
        "若刪除某設定，系統會自動回退到檔案中的設定值。"
    )

    # ── 定義可配置的 LLM 欄位 ────────────────────────────
    LLM_FIELDS = [
        {
            "key": "LEARNING_DEPLOYMENT",
            "label": "部署模式",
            "help": "「local」為 Mock 模式（不需 API Key），「cloud」使用真實 API",
            "type": "select",
            "options": ["local", "cloud"],
            "default": "local",
        },
        {
            "key": "LEARNING_API_KEY",
            "label": "DeepSeek API Key",
            "help": "從 https://platform.deepseek.com 取得",
            "type": "password",
            "default": "",
        },
        {
            "key": "LEARNING_LLM_MODEL",
            "label": "LLM 模型名稱",
            "help": "例如 deepseek-chat、deepseek-reasoner 等",
            "type": "text",
            "default": "deepseek-chat",
        },
        {
            "key": "LEARNING_LLM_URL",
            "label": "LLM API 端點 URL",
            "help": "OpenAI 相容 API 的 Base URL",
            "type": "text",
            "default": "https://api.deepseek.com/v1",
        },
        {
            "key": "LEARNING_WEB_SEARCH_API_KEY",
            "label": "Web Search API Key",
            "help": "SerpAPI 或 Bing Search API 的金鑰",
            "type": "password",
            "default": "",
        },
        {
            "key": "LEARNING_WEB_SEARCH_ENGINE",
            "label": "搜尋引擎",
            "help": "選擇使用 SerpAPI（Google 搜尋）或 Bing Search API",
            "type": "select",
            "options": ["serpapi", "bing"],
            "default": "serpapi",
        },
    ]

    # ── 讀取目前 DB 中的設定 ─────────────────────────────
    db_settings = get_all_settings()

    # ── 判斷每項設定的實際來源 ───────────────────────────
    def _get_source(key: str, default: str) -> str:
        """判斷設定的生效來源"""
        if key in db_settings and db_settings[key]:
            return "🗄️ 資料庫"
        try:
            import streamlit as st
            if st.secrets.get(key):
                return "🔒 Secrets"
        except Exception:
            pass
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        try:
            with open("config.toml", "rb") as f:
                toml_cfg = tomllib.load(f)
            if key in toml_cfg and toml_cfg[key]:
                return "📄 config.toml"
        except Exception:
            pass
        if key in os.environ and os.environ[key]:
            return "🌐 環境變數"
        return "⭐ 預設值"

    import os

    # ── 顯示目前設定總覽 ─────────────────────────────────
    st.markdown("#### 📋 目前設定狀態")

    status_data = []
    for field in LLM_FIELDS:
        current_value = config.get(field["key"], field["default"])
        source = _get_source(field["key"], field["default"])
        # 遮蔽 API Key 顯示
        display_value = current_value
        if field["type"] == "password" and current_value:
            display_value = current_value[:6] + "…" + current_value[-4:] if len(current_value) > 10 else "****"
        status_data.append({
            "設定項": field["label"],
            "目前值": display_value,
            "來源": source,
        })

    st.dataframe(status_data, use_container_width=True, hide_index=True)

    st.markdown("---")

    # ── 編輯表單 ─────────────────────────────────────────
    st.markdown("#### ✏️ 修改設定")

    with st.form("llm_config_form", clear_on_submit=False):
        new_values = {}
        for field in LLM_FIELDS:
            current = db_settings.get(field["key"], "")
            if field["type"] == "select":
                opts = field["options"]
                default_idx = opts.index(current) if current in opts else opts.index(field["default"])
                new_values[field["key"]] = st.selectbox(
                    f"{field['label']}",
                    options=opts,
                    index=default_idx,
                    help=field["help"],
                    key=f"cfg_{field['key']}",
                )
            elif field["type"] == "password":
                new_values[field["key"]] = st.text_input(
                    f"{field['label']}",
                    type="password",
                    value=current,
                    help=field["help"],
                    placeholder="輸入新值（留空表示不修改）",
                    key=f"cfg_{field['key']}",
                )
            else:
                new_values[field["key"]] = st.text_input(
                    f"{field['label']}",
                    value=current,
                    help=field["help"],
                    placeholder=field["default"],
                    key=f"cfg_{field['key']}",
                )

        col_save, col_reset = st.columns([1, 1])

        with col_save:
            submitted = st.form_submit_button("💾 儲存全部設定", use_container_width=True)

        with col_reset:
            reset_all = st.form_submit_button(
                "🗑️ 清除全部 DB 設定",
                use_container_width=True,
                help="刪除資料庫中的所有設定，讓系統回退到 config.toml / 預設值",
            )

    if submitted:
        changed = 0
        for field in LLM_FIELDS:
            key = field["key"]
            new_val = new_values[key].strip() if new_values[key] else ""
            old_val = db_settings.get(key, "")
            if new_val != old_val:
                if new_val:
                    set_setting(key, new_val)
                    changed += 1
                else:
                    delete_setting(key)
                    changed += 1
        if changed > 0:
            st.success(f"✅ 已更新 {changed} 項設定！變更將在下次載入設定時生效。")
            st.rerun()
        else:
            st.info("設定未變更。")

    if reset_all:
        keys_to_delete = [k for k in db_settings if k.startswith("LEARNING_")]
        for k in keys_to_delete:
            delete_setting(k)
        st.success(f"✅ 已清除 {len(keys_to_delete)} 項 DB 設定，系統將回退到 config.toml / 預設值。")
        st.rerun()

    # ── 個別刪除按鈕 ─────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔧 個別重設")

    db_key_list = [k for k in db_settings if k.startswith("LEARNING_")]
    if db_key_list:
        st.caption("以下設定已儲存在資料庫中，點擊刪除可回退到檔案設定值：")
        cols = st.columns(min(len(db_key_list), 3))
        for i, key in enumerate(db_key_list):
            with cols[i % 3]:
                field_label = key
                for f in LLM_FIELDS:
                    if f["key"] == key:
                        field_label = f["label"]
                        break
                if st.button(f"🗑️ {field_label}", key=f"del_{key}", use_container_width=True):
                    delete_setting(key)
                    st.success(f"已刪除「{field_label}」的 DB 設定")
                    st.rerun()
    else:
        st.info("目前沒有任何設定儲存在資料庫中，所有設定使用 config.toml / 預設值。")


def _render_oauth_config(config: dict) -> None:
    """繪製 OAuth 整合配置頁面，讓管理員在 UI 中管理第三方登入設定

    所有修改會直接寫入資料庫（app_settings 表），
    優先於 config.toml / secrets / JSON 憑證檔。
    """
    st.markdown("### 🔐 OAuth 第三方登入整合")
    st.caption(
        "在此修改的設定會儲存到資料庫，優先於 `config.toml` 與 `secrets.toml`。"
        "啟用並設定後，使用者即可在登入頁面使用對應的第三方帳號登入。"
    )

    # 從 auth 模組匯入常數
    from utils.auth import (
        OAUTH_PROVIDERS,
        _load_google_oauth_config,
        _load_facebook_oauth_config,
        _load_wechat_oauth_config,
    )

    # ── 定義各 Provider 的資訊 ─────────────────────────────
    providers_info = {
        "google": {
            "name": "Google",
            "icon": "🟢",
            "color": "#4285F4",
            "description": "Google 帳號登入。需在 Google Cloud Console 建立 OAuth 2.0 憑證。",
            "docs_url": "https://console.cloud.google.com/apis/credentials",
            "loader": _load_google_oauth_config,
        },
        "facebook": {
            "name": "Facebook",
            "icon": "🔵",
            "color": "#1877F2",
            "description": "Facebook 帳號登入。需在 Meta for Developers 建立應用程式。",
            "docs_url": "https://developers.facebook.com/apps/",
            "loader": _load_facebook_oauth_config,
        },
        "wechat": {
            "name": "WeChat",
            "icon": "🟢",
            "color": "#07C160",
            "description": "微信帳號登入。需在微信開放平台申請網站應用。",
            "docs_url": "https://open.weixin.qq.com/",
            "loader": _load_wechat_oauth_config,
        },
    }

    # ── 讀取目前 DB 中的設定 ─────────────────────────────
    db_settings = get_all_settings()

    st.markdown("#### 📋 目前設定狀態")

    # 顯示各 provider 狀態總覽
    status_data = []
    for key, info in providers_info.items():
        config_data = info["loader"]()
        enabled = config_data.get("enabled", False)
        has_creds = bool(config_data.get("client_id") and config_data.get("client_secret"))

        if not enabled:
            status_icon = "🔴 已停用"
        elif has_creds:
            status_icon = "🟢 已啟用"
        else:
            status_icon = "🟡 已啟用（未設定憑證）"

        cid_display = config_data.get("client_id", "-")
        if len(cid_display or "") > 30:
            cid_display = cid_display[:30] + "…"

        status_data.append({
            "Provider": info["name"],
            "狀態": status_icon,
            "Client ID": cid_display or "-",
            "來源": config_data.get("source", "-"),
        })

    st.dataframe(status_data, use_container_width=True, hide_index=True)

    st.markdown("---")
    st.markdown("#### ✏️ 修改設定")

    # ── 每個 Provider 一個 Expander ────────────────────────
    for provider_key, info in providers_info.items():
        current_config = info["loader"]()
        db_enabled = db_settings.get(f"OAUTH_{provider_key.upper()}_ENABLED", "")
        db_client_id = db_settings.get(f"OAUTH_{provider_key.upper()}_CLIENT_ID", "")
        db_client_secret = db_settings.get(f"OAUTH_{provider_key.upper()}_CLIENT_SECRET", "")

        # 判斷目前是否已啟用
        if db_enabled:
            is_enabled_db = db_enabled.lower() == "true"
        else:
            is_enabled_db = current_config.get("enabled", True)

        expander_title = f"{info['icon']} {info['name']}"
        if not current_config.get("enabled", True):
            expander_title += " （已停用）"
        elif current_config.get("client_id"):
            expander_title += " ✅"

        with st.expander(expander_title, expanded=False):
            st.caption(info["description"])
            st.caption(f"📖 [查看文件]({info['docs_url']})")

            # 顯示 redirect URI
            provider_meta = OAUTH_PROVIDERS.get(provider_key, {})
            redirect_uris = current_config.get("redirect_uris", ["未設定"])
            st.markdown(f"**Redirect URI**：`{redirect_uris[0]}`")
            st.caption("請將此 URI 加入 OAuth provider 的允許 redirect URI 清單中。")

            st.markdown("---")

            with st.form(f"oauth_form_{provider_key}", clear_on_submit=False):
                # Toggle 開關
                enabled = st.toggle(
                    f"啟用 {info['name']} 登入",
                    value=is_enabled_db,
                    help=f"關閉後使用者將無法使用 {info['name']} 帳號登入",
                    key=f"oauth_enable_{provider_key}",
                )

                # 目前設定來源
                source_label = current_config.get("source", "⭐ 預設值")
                st.caption(f"目前設定來源：{source_label}")

                # Client ID
                client_id = st.text_input(
                    "Client ID",
                    value=db_client_id if db_client_id else "",
                    placeholder=current_config.get("client_id", "") or "輸入 Client ID",
                    help=f"{info['name']} 應用程式的 Client ID / App ID",
                    key=f"oauth_cid_{provider_key}",
                )

                # Client Secret
                client_secret = st.text_input(
                    "Client Secret",
                    type="password",
                    value=db_client_secret if db_client_secret else "",
                    placeholder="輸入 Client Secret（留空表示不修改）",
                    help=f"{info['name']} 應用程式的 Client Secret / App Secret",
                    key=f"oauth_csec_{provider_key}",
                )

                col_save, col_delete = st.columns([1, 1])

                with col_save:
                    submitted = st.form_submit_button(
                        "💾 儲存設定", use_container_width=True,
                        key=f"oauth_save_{provider_key}",
                    )

                with col_delete:
                    clear = st.form_submit_button(
                        "🗑️ 清除 DB 設定", use_container_width=True,
                        help="刪除此 provider 的資料庫設定，回退到 config.toml / 憑證檔",
                        key=f"oauth_clear_{provider_key}",
                    )

            if submitted:
                prefix = f"OAUTH_{provider_key.upper()}"
                set_setting(f"{prefix}_ENABLED", "true" if enabled else "false")
                if client_id.strip():
                    set_setting(f"{prefix}_CLIENT_ID", client_id.strip())
                if client_secret.strip():
                    set_setting(f"{prefix}_CLIENT_SECRET", client_secret.strip())
                st.success(f"✅ {info['name']} 設定已儲存！")
                st.rerun()

            if clear:
                prefix = f"OAUTH_{provider_key.upper()}"
                for key in [f"{prefix}_ENABLED", f"{prefix}_CLIENT_ID", f"{prefix}_CLIENT_SECRET"]:
                    delete_setting(key)
                st.success(f"✅ 已清除 {info['name']} 的 DB 設定，回退到檔案設定值。")
                st.rerun()

    # ── 全部清除按鈕 ─────────────────────────────────────
    st.markdown("---")
    st.markdown("#### 🔧 全部重設")

    oauth_db_keys = [k for k in db_settings if k.startswith("OAUTH_")]
    if oauth_db_keys:
        st.caption(f"目前有 {len(oauth_db_keys)} 項 OAuth 設定儲存在資料庫中：")
        st.caption(", ".join(oauth_db_keys))
        if st.button("🗑️ 清除全部 OAuth DB 設定", use_container_width=True):
            for k in oauth_db_keys:
                delete_setting(k)
            st.success(f"✅ 已清除 {len(oauth_db_keys)} 項 OAuth DB 設定。")
            st.rerun()
    else:
        st.info("目前沒有任何 OAuth 設定儲存在資料庫中。")


def _export_users_csv() -> str:
    """將使用者資料匯出為 CSV 字串"""
    users = get_all_users()
    output = io.StringIO()
    writer = csv.writer(output)

    # 標題列
    writer.writerow([
        "使用者 ID", "使用者名稱", "電子郵件", "OAuth 提供者",
        "剩餘配額", "管理員", "註冊時間",
    ])

    for u in users:
        writer.writerow([
            u["id"],
            u["username"],
            u.get("email", ""),
            u.get("oauth_provider") or "local",
            u["credits"],
            "是" if u["is_admin"] else "否",
            u["created_at"],
        ])

    return output.getvalue()


def _export_usage_csv() -> str:
    """將使用紀錄匯出為 CSV 字串"""
    records = get_all_usage_records()
    output = io.StringIO()
    writer = csv.writer(output)

    # 標題列
    writer.writerow([
        "紀錄 ID", "使用者名稱", "類型", "檔案名稱",
        "扣點數", "時間",
    ])

    for r in records:
        writer.writerow([
            r["id"],
            r["username"],
            r["type"],
            r.get("file_name", ""),
            r["credits_used"],
            r["created_at"],
        ])

    return output.getvalue()


def is_first_login(user: dict, admin_default_password: str) -> bool:
    """檢查管理員是否使用預設密碼（首次登入）"""
    from utils.database import verify_password

    if not user.get("is_admin"):
        return False

    return verify_password(admin_default_password, user["password_hash"])
