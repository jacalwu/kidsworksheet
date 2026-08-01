"""
AI 學習助手 — Streamlit 主應用程式

功能：
1. 使用者註冊/登入（本地帳號 + OAuth）
2. Kid 管理（新增/編輯/刪除，選擇年級）
3. 上傳 PDF/Word 復習資料（支援 OCR）
4. 內容解析與結構化展示
5. 生成 Worksheet 或考試題目（使用 DeepSeek LLM）
6. 配額管理（每位使用者 100 次免費提問）
7. 管理員功能（查看/調整配額、匯出 CSV）
"""

import os
import json
import streamlit as st
from datetime import datetime, timezone

# ── 頁面設定（必須在第一個 st 指令之前） ──────────────────
st.set_page_config(
    page_title="AI 學習助手",
    page_icon="📚",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── 匯入自訂模組 ─────────────────────────────────────────
from utils.database import (
    init_db,
    set_db_path,
    ensure_admin_user,
    get_user_by_id,
    update_user_credits,
    deduct_credit,
    get_kids_by_user,
    create_kid,
    update_kid,
    delete_kid,
    get_kid_by_id,
    save_uploaded_file_record,
    get_uploaded_files_by_user,
    record_usage,
    get_usage_records_by_user,
)
from utils.auth import (
    init_session_state,
    get_current_user,
    require_login,
    login_user,
    logout_user,
    render_login_form,
    render_register_form,
    render_change_password_form,
    render_oauth_section,
    _render_inline_oauth_buttons,
    handle_oauth_callback,
)
from utils.parsers import (
    parse_file,
    format_parsed_content,
    get_parsed_json_for_display,
    get_pdf_page_count,
)
from utils.generator import (
    load_config,
    generate_document,
    create_docx_download,
    is_real_generation,
)
from utils.admin import render_admin_panel, is_first_login


# ── 初始化 ────────────────────────────────────────────────

def initialize_app() -> dict:
    """初始化應用程式：載入設定、初始化資料庫、建立管理員帳號"""
    config = load_config()

    # 設定資料庫路徑
    db_path = config.get("LEARNING_DATABASE_PATH", "learning_app.db")
    set_db_path(db_path)
    init_db()

    # 確保管理員帳號存在
    admin_username = config.get("LEARNING_ADMIN_USERNAME", "jacalwu")
    admin_password = config.get("LEARNING_ADMIN_PASSWORD", "jacalwu123456")
    ensure_admin_user(admin_username, admin_password)

    # 建立上傳目錄
    upload_dir = config.get("LEARNING_UPLOAD_DIR", "uploads")
    os.makedirs(upload_dir, exist_ok=True)

    # 初始化 session state
    init_session_state()

    return config


# ── 自訂 CSS 樣式 ─────────────────────────────────────────

def apply_custom_css() -> None:
    """套用自訂 CSS 樣式"""
    st.markdown(
        """
        <style>
        .main-header {
            font-size: 2rem;
            font-weight: bold;
            color: #1f77b4;
            margin-bottom: 1rem;
        }
        .sub-header {
            font-size: 1.2rem;
            color: #555;
            margin-bottom: 1.5rem;
        }
        .credit-badge {
            background-color: #e8f5e9;
            color: #2e7d32;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9rem;
            display: inline-block;
        }
        .credit-low {
            background-color: #fff3e0;
            color: #e65100;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9rem;
            display: inline-block;
        }
        .credit-zero {
            background-color: #ffebee;
            color: #c62828;
            padding: 8px 16px;
            border-radius: 20px;
            font-weight: bold;
            font-size: 0.9rem;
            display: inline-block;
        }
        .stButton > button {
            border-radius: 8px;
        }
        footer {visibility: hidden;}
        </style>
        """,
        unsafe_allow_html=True,
    )


# ── 主頁面路由 ────────────────────────────────────────────

def main() -> None:
    """主程式進入點"""
    config = initialize_app()
    apply_custom_css()

    # 處理 OAuth 回呼（若存在）
    handle_oauth_callback()

    # 根據登入狀態決定顯示哪個頁面
    if not st.session_state.get("logged_in"):
        render_unauthenticated_page(config)
    else:
        render_authenticated_app(config)


# ── 未登入頁面 ────────────────────────────────────────────

def render_unauthenticated_page(config: dict) -> None:
    """繪製未登入頁面（登入/註冊）"""
    st.markdown(
        '<div class="main-header">📚 AI 學習助手</div>',
        unsafe_allow_html=True,
    )
    st.markdown(
        '<div class="sub-header">上傳復習資料，AI 自動生成練習題與考試卷</div>',
        unsafe_allow_html=True,
    )

    # 登入 / 註冊分頁
    tab1, tab2 = st.tabs(["🔐 登入", "📝 註冊"])

    with tab1:
        # ── OAuth 第三方登入（醒目置頂） ──────────────────
        _render_inline_oauth_buttons()

        # ── 分隔線 ───────────────────────────────────────
        st.markdown("---")
        st.markdown(
            '<p style="text-align:center; color:#888;">── 或使用帳號密碼登入 ──</p>',
            unsafe_allow_html=True,
        )

        col_left, col_right = st.columns([1, 2])

        with col_left:
            render_login_form()

        with col_right:
            st.markdown("### 功能介紹")
            st.markdown(
                """
                ✨ **核心功能**：
                - 📄 上傳 PDF / Word 復習資料
                - 🔍 自動解析文件內容（支援 OCR）
                - 📝 一鍵生成練習題（Worksheet）
                - 📋 自動生成模擬考試卷
                - 👶 管理多個孩子的學習資料
                - 💯 每位使用者 100 次免費生成

                🚀 **快速開始**：
                1. 註冊帳號或直接登入
                2. 新增 Kid 並選擇年級
                3. 上傳復習資料
                4. 生成練習題或考試卷！
                """
            )

    with tab2:
        render_register_form()

    # 部署模式顯示
    deployment = config.get("LEARNING_DEPLOYMENT", "local")
    if deployment == "local":
        st.info(
            "🔧 **目前為 Mock 模式**：不呼叫真實 API，產生範例內容。"
            "將 `config.toml` 中的 `LEARNING_DEPLOYMENT` 設為 `\"cloud\"` "
            "並設定 API Key 以使用真實服務。"
        )


# ── 已登入應用程式 ────────────────────────────────────────

def render_authenticated_app(config: dict) -> None:
    """繪製已登入的主應用程式"""
    user = get_current_user()

    # 側邊欄
    with st.sidebar:
        render_sidebar(user, config)

    # 檢查是否為管理員首次登入（需修改密碼）
    if user and user.get("is_admin"):
        admin_default_pw = config.get("LEARNING_ADMIN_PASSWORD", "jacalwu123456")
        if is_first_login(user, admin_default_pw):
            st.warning(
                "⚠️ **安全性提醒**：您正在使用預設管理員密碼。"
                "請立即修改密碼以確保帳號安全。"
            )
            render_change_password_form()
            return

    # 根據導覽選擇顯示對應頁面
    page = st.session_state.get("current_page", "dashboard")

    if page == "dashboard":
        render_dashboard(user)
    elif page == "kids":
        render_kids_management(user)
    elif page == "upload":
        render_upload_page(user)
    elif page == "generate":
        render_generate_page(user, config)
    elif page == "history":
        render_history_page(user)
    elif page == "change_password":
        render_change_password_form()
    elif page == "admin":
        render_admin_panel(config)
    else:
        render_dashboard(user)


# ── 側邊欄 ────────────────────────────────────────────────

def render_sidebar(user: dict, config: dict) -> None:
    """繪製側邊導覽欄"""
    st.markdown("# 📚 AI 學習助手")

    # 使用者資訊
    st.markdown(f"### 👋 {user['username']}")

    # 配額顯示
    credits = user.get("credits", 0)
    credit_class = "credit-badge"
    if credits <= 0:
        credit_class = "credit-zero"
    elif credits <= 10:
        credit_class = "credit-low"

    st.markdown(
        f'<span class="{credit_class}">💯 剩餘配額：{credits} 次</span>',
        unsafe_allow_html=True,
    )

    if credits <= 0:
        st.error("⚠️ 配額已用盡，無法生成新內容。請聯繫管理員。")

    st.markdown("---")

    # 導覽選單
    nav_options = {
        "dashboard": "🏠 首頁",
        "kids": "👶 Kid 管理",
        "upload": "📤 上傳資料",
        "generate": "✨ 生成題目",
        "history": "📋 使用紀錄",
        "change_password": "🔑 修改密碼",
    }

    if user.get("is_admin"):
        nav_options["admin"] = "🛠️ 管理員控制台"

    # 使用 radio 作為導覽
    selected_label = st.radio(
        "導覽選單",
        options=list(nav_options.keys()),
        format_func=lambda x: nav_options[x],
        label_visibility="collapsed",
        key="nav_radio",
    )

    # 更新 current_page
    if selected_label != st.session_state.get("current_page"):
        st.session_state["current_page"] = selected_label
        st.rerun()

    st.markdown("---")

    # 登出按鈕
    if st.button("🚪 登出", use_container_width=True):
        logout_user()
        st.rerun()

    # 部署模式標籤
    deployment = config.get("LEARNING_DEPLOYMENT", "local")
    mode_label = "🟡 Mock 模式" if deployment == "local" else "🟢 雲端模式"
    st.caption(f"運行模式：{mode_label}")


# ── 首頁（Dashboard）───────────────────────────────────────

def render_dashboard(user: dict) -> None:
    """繪製首頁儀表板"""
    st.markdown(
        '<div class="main-header">🏠 首頁</div>',
        unsafe_allow_html=True,
    )

    # 快速統計
    kids = get_kids_by_user(user["id"])
    usage_records = get_usage_records_by_user(user["id"])

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        st.metric("👶 Kid 數量", len(kids))
    with col2:
        st.metric("📄 生成次數", len(usage_records))
    with col3:
        st.metric("💯 剩餘配額", user.get("credits", 0))
    with col4:
        # 本月使用量
        current_month = datetime.now().strftime("%Y-%m")
        monthly = sum(
            1 for r in usage_records
            if r["created_at"] and r["created_at"].startswith(current_month)
        )
        st.metric("📅 本月使用", monthly)

    st.markdown("---")

    # 快速操作
    st.markdown("### ⚡ 快速操作")

    qcol1, qcol2, qcol3 = st.columns(3)
    with qcol1:
        if st.button("👶 管理 Kid", use_container_width=True):
            st.session_state["current_page"] = "kids"
            st.rerun()
    with qcol2:
        if st.button("📤 上傳復習資料", use_container_width=True):
            st.session_state["current_page"] = "upload"
            st.rerun()
    with qcol3:
        if st.button("✨ 生成練習題", use_container_width=True):
            st.session_state["current_page"] = "generate"
            st.rerun()

    # 最近的 Kid 列表
    if kids:
        st.markdown("### 👶 您的 Kid")
        for kid in kids:
            kid_usage = sum(
                1 for r in usage_records
                if r["kid_id"] == kid["id"]
            )
            with st.expander(f"👶 {kid['name']} — {kid['grade']} 年級"):
                st.markdown(f"**年級**：{kid['grade']}")
                st.markdown(f"**建立時間**：{kid['created_at'][:10] if kid['created_at'] else 'N/A'}")
                st.markdown(f"**相關生成次數**：{kid_usage}")
    else:
        st.info("👶 還沒有新增 Kid，請先前往「Kid 管理」頁面新增。")

    # 最近使用紀錄
    if usage_records:
        st.markdown("### 📋 最近使用紀錄")
        for r in usage_records[:5]:
            type_emoji = "📝" if r["type"] == "worksheet" else "📋"
            type_label = "練習題" if r["type"] == "worksheet" else "考試卷"
            st.markdown(
                f"{type_emoji} **{type_label}** — "
                f"{r['file_name'] or '未指定檔案'} — "
                f"*{r['created_at'][:19] if r['created_at'] else 'N/A'}*"
            )
    else:
        st.info("📋 尚無使用紀錄。")


# ── Kid 管理頁面 ──────────────────────────────────────────

def render_kids_management(user: dict) -> None:
    """繪製 Kid 管理頁面"""
    st.markdown(
        '<div class="main-header">👶 Kid 管理</div>',
        unsafe_allow_html=True,
    )
    st.caption("管理孩子的資料，每位 Kid 可分別上傳復習資料與生成題目。")

    # 年級選項
    GRADE_OPTIONS = [
        "幼稚園", "小學一年級", "小學二年級", "小學三年級",
        "小學四年級", "小學五年級", "小學六年級",
        "國中一年級", "國中二年級", "國中三年級",
        "高中一年級", "高中二年級", "高中三年級",
        "大學", "其他",
    ]

    kids = get_kids_by_user(user["id"])

    # 新增 Kid
    with st.expander("➕ 新增 Kid", expanded=len(kids) == 0):
        col1, col2, col3 = st.columns([2, 2, 1])
        with col1:
            new_name = st.text_input("Kid 名稱", key="new_kid_name", placeholder="例如：小明")
        with col2:
            new_grade = st.selectbox("年級", GRADE_OPTIONS, key="new_kid_grade")
        with col3:
            st.markdown("<br>", unsafe_allow_html=True)
            if st.button("✅ 新增", use_container_width=True, key="btn_add_kid"):
                if new_name.strip():
                    create_kid(user["id"], new_name.strip(), new_grade)
                    st.success(f"已新增 Kid：{new_name.strip()}")
                    st.rerun()
                else:
                    st.error("請輸入 Kid 名稱。")

    # 現有 Kid 列表
    if kids:
        st.markdown("---")
        st.markdown("### 📋 現有 Kid")

        for kid in kids:
            with st.expander(
                f"👶 {kid['name']} — {kid['grade']}",
            ):
                # 編輯模式
                edit_col1, edit_col2 = st.columns([2, 2])
                with edit_col1:
                    edit_name = st.text_input(
                        "名稱", value=kid["name"], key=f"edit_name_{kid['id']}"
                    )
                with edit_col2:
                    edit_grade = st.selectbox(
                        "年級",
                        GRADE_OPTIONS,
                        index=GRADE_OPTIONS.index(kid["grade"])
                        if kid["grade"] in GRADE_OPTIONS
                        else 0,
                        key=f"edit_grade_{kid['id']}",
                    )

                btn_col1, btn_col2, btn_col3 = st.columns([1, 1, 2])
                with btn_col1:
                    if st.button("💾 儲存", key=f"save_kid_{kid['id']}"):
                        update_kid(kid["id"], edit_name, edit_grade)
                        st.success(f"已更新 {edit_name} 的資料。")
                        st.rerun()
                with btn_col2:
                    if st.button("🗑️ 刪除", key=f"delete_kid_{kid['id']}"):
                        delete_kid(kid["id"])
                        st.success(f"已刪除 {kid['name']}。")
                        st.rerun()
    else:
        st.info("尚無 Kid 資料，請點擊上方「新增 Kid」按鈕新增。")


# ── 上傳頁面 ──────────────────────────────────────────────

def render_upload_page(user: dict) -> None:
    """繪製檔案上傳與解析頁面"""
    st.markdown(
        '<div class="main-header">📤 上傳復習資料</div>',
        unsafe_allow_html=True,
    )
    st.caption("上傳 PDF 或 Word (.docx) 復習資料，系統將自動解析內容。")

    kids = get_kids_by_user(user["id"])

    if not kids:
        st.warning("⚠️ 請先新增 Kid 後再上傳資料。")
        if st.button("前往 Kid 管理"):
            st.session_state["current_page"] = "kids"
            st.rerun()
        return

    # 選擇 Kid
    kid_options = {f"{k['name']}（{k['grade']}）": k["id"] for k in kids}
    selected_kid_label = st.selectbox(
        "選擇 Kid", list(kid_options.keys()), key="upload_kid_select"
    )
    selected_kid_id = kid_options[selected_kid_label]

    # 上傳檔案
    uploaded_file = st.file_uploader(
        "選擇 PDF 或 Word (.docx) 檔案",
        type=["pdf", "docx", "doc"],
        key="file_uploader",
        help="支援 PDF（含多頁、圖片）與 Word 格式",
    )

    # OCR 選項（僅 PDF）
    use_ocr = False
    file_type = None
    if uploaded_file is not None:
        file_type = os.path.splitext(uploaded_file.name)[1].lower()
        if file_type == ".pdf":
            use_ocr = st.checkbox(
                "🔍 啟用 OCR 掃描",
                value=False,
                help="對 PDF 中的圖片進行文字辨識（需安裝 Tesseract 與 Poppler）",
            )

    if uploaded_file is not None:
        st.markdown("---")

        # 檔案資訊
        file_size_kb = len(uploaded_file.getvalue()) / 1024
        st.markdown(f"**📄 檔案名稱**：{uploaded_file.name}")
        st.markdown(f"**📏 檔案大小**：{file_size_kb:.1f} KB")

        if file_type == ".pdf":
            page_count = get_pdf_page_count(uploaded_file.getvalue())
            st.markdown(f"**📑 頁數**：{page_count}")

        # 解析按鈕
        if st.button("🔍 預覽檔案資料", use_container_width=True, key="btn_parse"):
            with st.spinner("正在解析檔案內容..."):
                parsed = parse_file(
                    uploaded_file.getvalue(),
                    uploaded_file.name,
                    use_ocr=use_ocr,
                )

                # 儲存解析結果到 session state（以便生成頁面使用）
                st.session_state["last_parsed"] = parsed
                st.session_state["last_parsed_file_name"] = uploaded_file.name
                st.session_state["last_parsed_kid_id"] = selected_kid_id

                # 儲存到資料庫
                content_json = get_parsed_json_for_display(parsed)
                page_count = parsed.get("metadata", {}).get("pages", 0)
                save_uploaded_file_record(
                    user["id"],
                    uploaded_file.name,
                    file_type or "unknown",
                    kid_id=selected_kid_id,
                    page_count=page_count,
                    parsed_json=content_json,
                )

                st.success("✅ 檔案解析完成！")

                # 顯示解析結果
                st.markdown("### 📋 解析結果")

                # Metadata
                st.json(parsed.get("metadata", {}))

                # 內容預覽
                formatted = format_parsed_content(parsed)
                preview = formatted[:3000]
                if len(formatted) > 3000:
                    preview += f"\n\n...（共 {len(formatted)} 字元，僅顯示前 3000 字元）"

                with st.expander("📝 內容預覽", expanded=True):
                    st.text_area(
                        "解析內容",
                        preview,
                        height=300,
                        key="parsed_preview",
                        disabled=True,
                    )

                st.info(
                    "💡 解析完成！請前往「✨ 生成題目」頁面，"
                    "選擇此檔案來生成練習題或考試卷。"
                )

    # 上傳歷史
    st.markdown("---")
    st.markdown("### 📚 上傳歷史")

    uploads = get_uploaded_files_by_user(user["id"])
    if uploads:
        for u in uploads[:10]:
            st.markdown(
                f"📄 **{u['file_name']}** — "
                f"{u['file_type']} — "
                f"{u['page_count']} 頁 — "
                f"*{u['created_at'][:19] if u['created_at'] else 'N/A'}*"
            )
    else:
        st.info("尚無上傳紀錄。")


# ── 生成題目頁面 ──────────────────────────────────────────

def render_generate_page(user: dict, config: dict) -> None:
    """繪製生成 worksheet/exam 頁面"""
    st.markdown(
        '<div class="main-header">✨ 生成題目</div>',
        unsafe_allow_html=True,
    )
    st.caption("根據上傳的復習資料，使用 AI 生成練習題或考試卷。")

    # 檢查配額
    credits = user.get("credits", 0)
    if credits <= 0:
        st.error("❌ 您的配額已用盡，無法生成新內容。請聯繫管理員（jacalwu）調整配額。")
        return

    kids = get_kids_by_user(user["id"])
    if not kids:
        st.warning("⚠️ 請先新增 Kid 後再生成題目。")
        return

    # 取得上傳紀錄
    uploads = get_uploaded_files_by_user(user["id"])
    has_parsed_in_session = "last_parsed" in st.session_state

    col_left, col_right = st.columns([1, 1])

    with col_left:
        st.markdown("### ⚙️ 生成設定")

        # 選擇 Kid
        kid_options = {f"{k['name']}（{k['grade']}）": k for k in kids}
        selected_kid_label = st.selectbox(
            "選擇 Kid", list(kid_options.keys()), key="gen_kid_select"
        )
        selected_kid = kid_options[selected_kid_label]

        # 選擇生成類型
        generate_type = st.radio(
            "生成類型",
            options=["worksheet", "exam"],
            format_func=lambda x: "📝 練習題（Worksheet）" if x == "worksheet" else "📋 考試卷（Exam）",
            key="gen_type",
        )

        # 是否使用網路搜尋
        use_search = st.checkbox(
            "🌐 使用網路搜尋補充資料",
            value=False,
            help="啟用後將搜尋相關補充資料，提升題目豐富度",
        )

        # 顯示使用說明
        type_desc = {
            "worksheet": "生成包含選擇題、填充題、簡答題的練習題，適合日常復習。",
            "exam": "生成包含選擇題、填充題、申論題的正式考試卷，附配分與評分標準。",
        }
        st.info(type_desc.get(generate_type, ""))

    with col_right:
        st.markdown("### 📄 復習資料來源")

        source_option = st.radio(
            "選擇資料來源",
            options=["files", "latest", "paste"],
            format_func=lambda x: {
                "files": "📚 從上傳紀錄選擇（可多選）",
                "latest": "🆕 使用最近解析的檔案",
                "paste": "📋 直接貼上文字內容",
            }.get(x, x),
            key="source_option",
        )

        content_text = ""
        selected_files_info = []  # 記錄選中檔案資訊，供 record_usage 使用

        if source_option == "files":
            if uploads:
                # 多選檔案
                file_options = {}
                for u in uploads:
                    label = f"📄 {u['file_name']}（{u['file_type']}｜{u['page_count']}頁｜{u['created_at'][:19] if u['created_at'] else 'N/A'}）"
                    file_options[label] = u

                selected_labels = st.multiselect(
                    "選擇要使用的檔案（可多選）",
                    options=list(file_options.keys()),
                    key="multi_file_select",
                    help="選中的檔案內容將會合併後一起生成題目",
                )

                if selected_labels:
                    merged_parts = []
                    for label in selected_labels:
                        u = file_options[label]
                        selected_files_info.append(u)
                        # 從 DB 讀取解析內容
                        parsed_json_str = u.get("parsed_json") or "{}"
                        try:
                            import json as json_lib
                            parsed_data = json_lib.loads(parsed_json_str)
                            file_content = format_parsed_content(parsed_data)
                        except Exception:
                            file_content = parsed_json_str

                        merged_parts.append(
                            f"### 檔案：{u['file_name']}\n\n{file_content}"
                        )

                    content_text = "\n\n---\n\n".join(merged_parts)
                    st.success(f"✅ 已載入 {len(selected_labels)} 個檔案（合計 {len(content_text)} 字元）")

                    with st.expander("📝 合併內容預覽"):
                        preview = content_text[:2000]
                        if len(content_text) > 2000:
                            preview += f"\n\n...（共 {len(content_text)} 字元，僅顯示前 2000 字元）"
                        st.text(preview)
                else:
                    st.info("請從上方列表中選擇至少一個檔案。")
            else:
                st.warning("尚無上傳紀錄，請先前往「📤 上傳資料」頁面上傳並解析檔案。")
                if st.button("前往上傳頁面"):
                    st.session_state["current_page"] = "upload"
                    st.rerun()

        elif source_option == "latest":
            if has_parsed_in_session:
                parsed = st.session_state["last_parsed"]
                file_name = st.session_state.get("last_parsed_file_name", "未知")
                content_text = format_parsed_content(parsed)
                st.success(f"✅ 已載入：{file_name}（{len(content_text)} 字元）")
                with st.expander("📝 預覽內容"):
                    st.text(content_text[:1500] + ("..." if len(content_text) > 1500 else ""))
            else:
                st.warning("尚未解析任何檔案，請先前往「📤 上傳資料」頁面上傳並解析檔案。")
                if st.button("前往上傳頁面"):
                    st.session_state["current_page"] = "upload"
                    st.rerun()
        else:
            content_text = st.text_area(
                "請貼上復習資料內容",
                height=250,
                placeholder="在此貼上要生成題目的文字內容...",
                key="pasted_content",
            )

    st.markdown("---")

    # ── 使用者自訂 Prompt 微調 ────────────────────────────
    st.markdown("### ✏️ 微調選項（選填）")
    user_prompt_hint = st.text_area(
        "自訂生成提示",
        height=80,
        placeholder="例如：題目要簡單一點、多出選擇題、加入生活化的例子、重點放在第三章...",
        help="在此輸入對題目生成的額外要求。輸入內容會經過安全過濾以防注入攻擊。",
        key="user_prompt_hint",
    )

    st.markdown("---")

    # 生成按鈕
    gen_col1, gen_col2 = st.columns([3, 1])
    with gen_col1:
        generate_btn = st.button(
            f"🚀 生成{'練習題' if generate_type == 'worksheet' else '考試卷'}（消耗 1 點配額）",
            use_container_width=True,
            type="primary",
            disabled=(not content_text),
        )
    with gen_col2:
        st.markdown(f'<span class="credit-badge">剩餘：{credits} 次</span>', unsafe_allow_html=True)

    if generate_btn and content_text:
        # 扣除配額
        if not deduct_credit(user["id"]):
            st.error("❌ 配額扣除失敗，請聯繫管理員。")
            return

        # 顯示進度
        progress_bar = st.progress(0, "正在準備生成...")
        status_text = st.empty()

        try:
            # 更新進度
            progress_bar.progress(20, "正在處理復習資料...")
            status_text.info("📝 正在分析復習資料內容...")

            # 生成
            progress_bar.progress(40, "正在呼叫 AI 模型...")
            status_text.info("🤖 正在呼叫 AI 模型生成題目...")

            markdown_content, model_used = generate_document(
                content_text,
                selected_kid["name"],
                selected_kid["grade"],
                generate_type,
                use_search=use_search,
                config=config,
                user_prompt_hint=user_prompt_hint,
            )

            progress_bar.progress(70, "正在建立下載檔案...")
            status_text.info("📄 正在建立 Word 文件...")

            # 建立下載檔案
            docx_bytes, filename = create_docx_download(
                markdown_content, generate_type, selected_kid["name"]
            )

            # 記錄使用
            # 合併選中檔案名稱作為記錄
            if selected_files_info:
                record_file_name = " + ".join(
                    u["file_name"] for u in selected_files_info
                )
            else:
                record_file_name = st.session_state.get("last_parsed_file_name", "")
            record_usage(
                user["id"],
                generate_type,
                kid_id=selected_kid["id"],
                file_name=record_file_name,
            )

            progress_bar.progress(100, "完成！")
            status_text.success("✅ 生成完成！")

            # 更新 session state 中的配額
            st.session_state["user"]["credits"] -= 1

            # 顯示結果
            st.markdown("---")
            st.markdown("### 🎉 生成結果")

            # 顯示內容
            with st.expander("📝 查看內容", expanded=True):
                st.markdown(markdown_content)

            # 下載按鈕
            st.download_button(
                label=f"📥 下載 Word 檔案（{filename}）",
                data=docx_bytes,
                file_name=filename,
                mime="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                use_container_width=True,
            )

            # 顯示使用的模型
            is_real = is_real_generation(config)
            st.caption(
                f"🤖 模型：{model_used} | "
                f"{'🟢 真實生成' if is_real else '🟡 Mock 模式'} | "
                f"剩餘配額：{st.session_state['user']['credits']} 次"
            )

            # 提示重新整理配額
            st.info("💡 配額已更新，請查看側邊欄確認剩餘次數。")

        except Exception as e:
            progress_bar.empty()
            status_text.error(f"❌ 生成失敗：{str(e)}")
            st.error(
                "生成過程中發生錯誤。請確認 API 設定正確，"
                "或將 LEARNING_DEPLOYMENT 設為 'local' 使用 Mock 模式測試。"
            )


# ── 使用紀錄頁面 ──────────────────────────────────────────

def render_history_page(user: dict) -> None:
    """繪製使用紀錄頁面"""
    st.markdown(
        '<div class="main-header">📋 使用紀錄</div>',
        unsafe_allow_html=True,
    )

    records = get_usage_records_by_user(user["id"])

    if not records:
        st.info("尚無使用紀錄。")
        return

    # 統計
    worksheet_count = sum(1 for r in records if r["type"] == "worksheet")
    exam_count = sum(1 for r in records if r["type"] == "exam")

    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("📝 練習題", worksheet_count)
    with col2:
        st.metric("📋 考試卷", exam_count)
    with col3:
        st.metric("💯 總計", len(records))

    st.markdown("---")

    # 紀錄列表
    for r in records:
        type_emoji = "📝" if r["type"] == "worksheet" else "📋"
        type_label = "練習題（Worksheet）" if r["type"] == "worksheet" else "考試卷（Exam）"

        with st.expander(
            f"{type_emoji} {type_label} — "
            f"{r['created_at'][:19] if r['created_at'] else 'N/A'}"
        ):
            st.markdown(f"**類型**：{type_label}")
            st.markdown(f"**檔案**：{r['file_name'] or '未指定'}")
            st.markdown(f"**消耗配額**：{r['credits_used']} 點")
            st.markdown(f"**時間**：{r['created_at']}")


# ── 程式進入點 ────────────────────────────────────────────

if __name__ == "__main__":
    main()
