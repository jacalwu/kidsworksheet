"""
認證模組：處理使用者註冊、登入、OAuth 登錄與 session 管理。

支援：
- 本地帳號密碼認證（主要方式，適用於所有環境）
- Google OAuth（本地測試可用；Streamlit Cloud 需設定 redirect URI）
- Facebook OAuth（需自行申請 App ID；Streamlit Cloud 有回呼限制）
- WeChat OAuth（需微信開放平台帳號，僅限中國大陸使用）

注意：
  Streamlit Cloud 的 URL 是動態分配的，OAuth 回呼（redirect_uri）可能無法固定。
  在 Streamlit Cloud 上建議以本地帳號密碼為主要認證方式。
  若要在本地測試 OAuth，請在對應平台設定 redirect_uri 為 http://localhost:8501/oauth_callback
"""

import streamlit as st
from typing import Optional, Callable
import urllib.parse

from utils.database import (
    create_user,
    get_user_by_username,
    authenticate_user,
    get_user_by_id,
    update_user_password,
)


# ── 常數 ──────────────────────────────────────────────────

OAUTH_PROVIDERS = {
    "google": {
        "name": "Google",
        "authorize_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "userinfo_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scope": "openid email profile",
    },
    "facebook": {
        "name": "Facebook",
        "authorize_url": "https://www.facebook.com/v18.0/dialog/oauth",
        "token_url": "https://graph.facebook.com/v18.0/oauth/access_token",
        "userinfo_url": "https://graph.facebook.com/me?fields=id,name,email",
        "scope": "email public_profile",
    },
    "wechat": {
        "name": "WeChat",
        "authorize_url": "https://open.weixin.qq.com/connect/qrconnect",
        "token_url": "https://api.weixin.qq.com/sns/oauth2/access_token",
        "userinfo_url": "https://api.weixin.qq.com/sns/userinfo",
        "scope": "snsapi_login",
    },
}


# ── Session State 初始化 ──────────────────────────────────

def init_session_state() -> None:
    """初始化 Streamlit session state 中的認證相關變數"""
    defaults = {
        "user": None,
        "logged_in": False,
        "is_admin": False,
        "oauth_state": None,
        "show_change_password": False,
    }
    for key, value in defaults.items():
        if key not in st.session_state:
            st.session_state[key] = value


def login_user(user_row) -> None:
    """將使用者資訊寫入 session state"""
    st.session_state["user"] = dict(user_row)
    st.session_state["logged_in"] = True
    st.session_state["is_admin"] = bool(user_row["is_admin"])
    st.session_state["show_change_password"] = False


def logout_user() -> None:
    """清除 session state 中的使用者資訊"""
    st.session_state["user"] = None
    st.session_state["logged_in"] = False
    st.session_state["is_admin"] = False
    st.session_state["show_change_password"] = False


def get_current_user() -> Optional[dict]:
    """取得目前登入的使用者"""
    if st.session_state.get("logged_in"):
        return st.session_state.get("user")
    return None


def require_login() -> Optional[dict]:
    """要求登入；若未登入則顯示提示並回傳 None"""
    user = get_current_user()
    if user is None:
        st.warning("⚠️ 請先登入以使用此功能。")
        return None
    return user


# ── 本地認證 UI ───────────────────────────────────────────

def render_login_form() -> None:
    """繪製登入表單"""
    st.markdown("## 🔐 登入")

    with st.form("login_form", clear_on_submit=False):
        username = st.text_input("使用者名稱", key="login_username")
        password = st.text_input("密碼", type="password", key="login_password")
        submitted = st.form_submit_button("登入", use_container_width=True)

        if submitted:
            if not username or not password:
                st.error("請輸入使用者名稱與密碼。")
                return

            user = authenticate_user(username, password)
            if user:
                login_user(user)
                st.success(f"歡迎回來，{username}！")
                st.rerun()
            else:
                st.error("使用者名稱或密碼錯誤。")


def render_register_form() -> None:
    """繪製註冊表單"""
    st.markdown("## 📝 註冊新帳號")

    with st.form("register_form", clear_on_submit=False):
        username = st.text_input("使用者名稱", key="reg_username")
        email = st.text_input("電子郵件（選填）", key="reg_email")
        password = st.text_input("密碼", type="password", key="reg_password")
        password2 = st.text_input("確認密碼", type="password", key="reg_password2")
        submitted = st.form_submit_button("註冊", use_container_width=True)

        if submitted:
            # 基本驗證
            if not username or not password:
                st.error("使用者名稱與密碼為必填。")
                return
            if len(username) < 3:
                st.error("使用者名稱至少需要 3 個字元。")
                return
            if len(password) < 6:
                st.error("密碼至少需要 6 個字元。")
                return
            if password != password2:
                st.error("兩次輸入的密碼不一致。")
                return

            # 檢查是否已存在
            existing = get_user_by_username(username)
            if existing:
                st.error("此使用者名稱已被使用，請選擇其他名稱。")
                return

            user_id = create_user(username, password, email)
            if user_id:
                st.success("註冊成功！請前往登入頁面。")
            else:
                st.error("註冊失敗，請稍後再試。")


def render_change_password_form() -> None:
    """繪製修改密碼表單"""
    st.markdown("## 🔑 修改密碼")

    user = get_current_user()
    if not user:
        return

    with st.form("change_password_form", clear_on_submit=False):
        old_password = st.text_input("目前密碼", type="password", key="old_pw")
        new_password = st.text_input("新密碼", type="password", key="new_pw")
        new_password2 = st.text_input("確認新密碼", type="password", key="new_pw2")
        submitted = st.form_submit_button("更新密碼", use_container_width=True)

        if submitted:
            if not old_password or not new_password:
                st.error("所有欄位皆為必填。")
                return
            if len(new_password) < 6:
                st.error("新密碼至少需要 6 個字元。")
                return
            if new_password != new_password2:
                st.error("兩次輸入的新密碼不一致。")
                return

            # 再驗證一次目前密碼
            authed = authenticate_user(user["username"], old_password)
            if not authed:
                st.error("目前密碼輸入錯誤。")
                return

            update_user_password(user["id"], new_password)
            st.success("密碼更新成功！")
            st.session_state["show_change_password"] = False
            st.rerun()


# ── OAuth 輔助函式 ────────────────────────────────────────

def build_oauth_url(provider: str, client_id: str, redirect_uri: str) -> str:
    """建立 OAuth 授權 URL"""
    config = OAUTH_PROVIDERS.get(provider)
    if not config:
        return ""

    from secrets import token_urlsafe

    state = token_urlsafe(32)
    st.session_state["oauth_state"] = state

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
    }

    if provider == "wechat":
        # WeChat 使用特殊格式
        url = f"{config['authorize_url']}?appid={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}&response_type=code&scope={config['scope']}&state={state}#wechat_redirect"
        return url

    return f"{config['authorize_url']}?{urllib.parse.urlencode(params)}"


def render_oauth_section() -> None:
    """繪製 OAuth 登入選項區塊

    此區塊提供 Google OAuth 的詳細實作指引。
    Facebook 與 WeChat OAuth 在 Streamlit Cloud 環境有較多限制，
    此處提供說明與程式碼框架。
    """
    st.markdown("---")
    st.markdown("### 🌐 第三方登入")

    # 嘗試讀取 OAuth 設定
    google_client_id = None
    try:
        google_client_id = st.secrets.get("GOOGLE_CLIENT_ID", "")
    except Exception:
        pass

    # 也嘗試從 config.toml 讀取
    if not google_client_id:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib
        try:
            with open("config.toml", "rb") as f:
                cfg = tomllib.load(f)
            google_client_id = cfg.get("GOOGLE_CLIENT_ID", "")
        except Exception:
            pass

    # Google OAuth
    if google_client_id:
        redirect_uri = "http://localhost:8501/oauth_callback"
        google_url = build_oauth_url("google", google_client_id, redirect_uri)

        st.markdown(
            f"""
            <a href="{google_url}" target="_self">
                <button style="
                    background-color: #4285F4; color: white; border: none;
                    padding: 10px 20px; border-radius: 5px; cursor: pointer;
                    font-size: 16px; width: 100%;">
                    🔵 使用 Google 帳號登入
                </button>
            </a>
            """,
            unsafe_allow_html=True,
        )
    else:
        st.info(
            "💡 **Google OAuth 未設定**\n\n"
            "若要啟用 Google 登入，請在 `config.toml` 或 `.streamlit/secrets.toml` 中設定：\n"
            "```toml\n"
            'GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"\n'
            'GOOGLE_CLIENT_SECRET = "your-client-secret"\n'
            "```\n"
            "並在 Google Cloud Console 設定 redirect URI 為 "
            "`http://localhost:8501/oauth_callback`"
        )

    st.caption(
        "📌 **Facebook / WeChat OAuth 說明**：由於 Streamlit Cloud 的 URL 為動態分配，"
        "這些平台要求固定的 redirect URI，因此僅建議在自有網域部署時使用。"
        "詳見 README.md 的「OAuth 設定」章節。"
    )


def handle_oauth_callback() -> Optional[dict]:
    """處理 OAuth 回呼（從 URL query params 取得 code 並交換 token）

    此為框架程式碼，實際部署需搭配 OAuth provider SDK（如 authlib）。
    目前回傳 None，並在 UI 顯示提示。
    """
    query_params = st.query_params
    code = query_params.get("code", None)
    state = query_params.get("state", None)

    if code and state:
        st.info(
            "🔧 OAuth 回呼已收到。完整的 token 交換邏輯需部署時設定。\n"
            "請參考 README.md 中的 OAuth 設定章節，使用 `authlib` 完成整合。"
        )
        # 清除 query params
        st.query_params.clear()
    return None
