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
)


def render_admin_panel() -> None:
    """繪製管理員控制面板"""
    st.markdown("## 🛠️ 管理員控制台")

    if not st.session_state.get("is_admin"):
        st.error("❌ 您沒有管理員權限。")
        return

    # 分頁
    tab1, tab2, tab3 = st.tabs(["👥 使用者管理", "📊 使用紀錄", "📥 匯出資料"])

    with tab1:
        _render_user_management()

    with tab2:
        _render_usage_records()

    with tab3:
        _render_export()


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
