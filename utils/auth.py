"""
認證模組：處理使用者註冊、登入、OAuth 登錄與 session 管理。

支援：
- 本地帳號密碼認證（主要方式，適用於所有環境）
- Google OAuth（完整實作：授權 → token 交換 → 使用者資訊 → 帳號建立/登入）
- Facebook OAuth（需自行申請 App ID）
- WeChat OAuth（需微信開放平台帳號，僅限中國大陸使用）
"""

import os
import json
import streamlit as st
from typing import Optional, Callable
import urllib.parse
import secrets as secrets_lib

from utils.database import (
    create_user,
    get_user_by_username,
    authenticate_user,
    get_user_by_id,
    update_user_password,
    get_connection,
    hash_password,
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


# ── OAuth Provider 設定鍵名對照 ─────────────────────────────

# 每個 provider 在各設定來源中的鍵名前綴
PROVIDER_CONFIG_KEYS = {
    "google": {
        "db_prefix": "OAUTH_GOOGLE",
        "secrets_client_id": "GOOGLE_CLIENT_ID",
        "secrets_client_secret": "GOOGLE_CLIENT_SECRET",
        "default_redirect_uri": "http://localhost:8501/oauth_callback",
        "has_json_file": True,  # Google 可從 client_secret_*.json 讀取
    },
    "facebook": {
        "db_prefix": "OAUTH_FACEBOOK",
        "secrets_client_id": "FACEBOOK_CLIENT_ID",
        "secrets_client_secret": "FACEBOOK_CLIENT_SECRET",
        "default_redirect_uri": "http://localhost:8501/oauth_callback",
        "has_json_file": False,
    },
    "wechat": {
        "db_prefix": "OAUTH_WECHAT",
        "secrets_client_id": "WECHAT_CLIENT_ID",
        "secrets_client_secret": "WECHAT_CLIENT_SECRET",
        "default_redirect_uri": "http://localhost:8501/oauth_callback",
        "has_json_file": False,
    },
}


def _load_oauth_config_from_db(provider: str) -> dict:
    """從資料庫讀取 OAuth 設定（最高優先層級）

    Args:
        provider: "google" / "facebook" / "wechat"

    Returns:
        dict: {"enabled": bool, "client_id": str, "client_secret": str}
              若 DB 中無設定則回傳空值
    """
    try:
        from utils.database import get_all_settings
    except ImportError:
        return {"enabled": True, "client_id": "", "client_secret": ""}

    try:
        db_settings = get_all_settings()
        prefix = PROVIDER_CONFIG_KEYS[provider]["db_prefix"]
        enabled_str = db_settings.get(f"{prefix}_ENABLED", "")
        if enabled_str:
            enabled = enabled_str.lower() == "true"
        else:
            enabled = True  # 預設啟用（若未在 DB 中明確停用）
        return {
            "enabled": enabled,
            "client_id": db_settings.get(f"{prefix}_CLIENT_ID", ""),
            "client_secret": db_settings.get(f"{prefix}_CLIENT_SECRET", ""),
            "source": "🗄️ 資料庫",
        }
    except Exception:
        return {"enabled": True, "client_id": "", "client_secret": "", "source": ""}


# ── OAuth 設定讀取 ──────────────────────────────────────────

def _load_google_oauth_config() -> dict:
    """從多個來源讀取 Google OAuth 設定

    優先順序：
    1. 資料庫 app_settings（管理員 UI 設定，最高優先）
    2. client_secret_*.json 檔案（Google Cloud Console 下載的憑證檔）
    3. Streamlit secrets（GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET）
    4. config.toml（GOOGLE_CLIENT_ID / GOOGLE_CLIENT_SECRET）

    Returns:
        dict: {"enabled": bool, "client_id": str, "client_secret": str,
               "redirect_uris": list, "source": str}
    """
    result = {
        "enabled": True,
        "client_id": "",
        "client_secret": "",
        "redirect_uris": ["http://localhost:8501/oauth_callback"],
        "source": "⭐ 未設定",
    }

    # 0. 嘗試從資料庫讀取（最高優先）
    db_config = _load_oauth_config_from_db("google")
    if not db_config["enabled"]:
        result["enabled"] = False
        result["source"] = "🗄️ 資料庫（已停用）"
        return result
    if db_config["client_id"] and db_config["client_secret"]:
        result["enabled"] = True
        result["client_id"] = db_config["client_id"]
        result["client_secret"] = db_config["client_secret"]
        result["source"] = "🗄️ 資料庫"
        return result

    # 1. 嘗試從 Google 憑證 JSON 檔案讀取
    json_paths = []
    try:
        for fname in os.listdir("."):
            if fname.startswith("client_secret_") and fname.endswith(".json"):
                json_paths.append(fname)
    except Exception:
        pass
    streamlit_dir = ".streamlit"
    if os.path.isdir(streamlit_dir):
        try:
            for fname in os.listdir(streamlit_dir):
                if fname.startswith("client_secret_") and fname.endswith(".json"):
                    json_paths.append(os.path.join(streamlit_dir, fname))
        except Exception:
            pass

    for json_path in json_paths[:1]:
        try:
            with open(json_path, "r") as f:
                data = json.load(f)
            web = data.get("web", {})
            result["client_id"] = web.get("client_id", "")
            result["client_secret"] = web.get("client_secret", "")
            uris = web.get("redirect_uris", [])
            if uris:
                result["redirect_uris"] = uris
            if result["client_id"] and result["client_secret"]:
                result["source"] = "📄 JSON 憑證檔"
                return result
        except Exception:
            pass

    # 2. 嘗試從 Streamlit secrets 讀取
    try:
        cid = st.secrets.get("GOOGLE_CLIENT_ID", "")
        csec = st.secrets.get("GOOGLE_CLIENT_SECRET", "")
        if cid and csec:
            result["client_id"] = cid
            result["client_secret"] = csec
            result["source"] = "🔒 Secrets"
            return result
    except Exception:
        pass

    # 3. 嘗試從 config.toml 讀取
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    try:
        with open("config.toml", "rb") as f:
            cfg = tomllib.load(f)
        cid = cfg.get("GOOGLE_CLIENT_ID", "")
        csec = cfg.get("GOOGLE_CLIENT_SECRET", "")
        if cid and csec:
            result["client_id"] = cid
            result["client_secret"] = csec
            result["source"] = "📄 config.toml"
    except Exception:
        pass

    return result


def _load_facebook_oauth_config() -> dict:
    """從多個來源讀取 Facebook OAuth 設定

    優先順序：DB > Streamlit secrets > config.toml

    Returns:
        dict: {"enabled": bool, "client_id": str, "client_secret": str,
               "redirect_uris": list, "source": str}
    """
    return _load_generic_oauth_config("facebook")


def _load_wechat_oauth_config() -> dict:
    """從多個來源讀取 WeChat OAuth 設定

    優先順序：DB > Streamlit secrets > config.toml

    Returns:
        dict: {"enabled": bool, "client_id": str, "client_secret": str,
               "redirect_uris": list, "source": str}
    """
    return _load_generic_oauth_config("wechat")


def _load_generic_oauth_config(provider: str) -> dict:
    """通用的 OAuth 設定讀取函式（適用於 Facebook / WeChat）

    優先順序：DB > Streamlit secrets > config.toml

    Args:
        provider: "facebook" / "wechat"

    Returns:
        dict: {"enabled": bool, "client_id": str, "client_secret": str,
               "redirect_uris": list, "source": str}
    """
    keys = PROVIDER_CONFIG_KEYS[provider]
    result = {
        "enabled": True,
        "client_id": "",
        "client_secret": "",
        "redirect_uris": [keys["default_redirect_uri"]],
        "source": "⭐ 未設定",
    }

    # 0. 資料庫（最高優先）
    db_config = _load_oauth_config_from_db(provider)
    if not db_config["enabled"]:
        result["enabled"] = False
        result["source"] = "🗄️ 資料庫（已停用）"
        return result
    if db_config["client_id"] and db_config["client_secret"]:
        result["enabled"] = True
        result["client_id"] = db_config["client_id"]
        result["client_secret"] = db_config["client_secret"]
        result["source"] = "🗄️ 資料庫"
        return result

    # 1. Streamlit secrets
    try:
        cid = st.secrets.get(keys["secrets_client_id"], "")
        csec = st.secrets.get(keys["secrets_client_secret"], "")
        if cid and csec:
            result["client_id"] = cid
            result["client_secret"] = csec
            result["source"] = "🔒 Secrets"
            return result
    except Exception:
        pass

    # 2. config.toml
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib
    try:
        with open("config.toml", "rb") as f:
            cfg = tomllib.load(f)
        cid = cfg.get(keys["secrets_client_id"], "")
        csec = cfg.get(keys["secrets_client_secret"], "")
        if cid and csec:
            result["client_id"] = cid
            result["client_secret"] = csec
            result["source"] = "📄 config.toml"
    except Exception:
        pass

    return result


def _get_redirect_uri(allowed_uris: list[str]) -> str:
    """根據目前執行環境選擇合適的 redirect URI

    若目前執行在 localhost 則優先使用 localhost URI；
    若在部署環境（Streamlit Cloud）則優先使用非 localhost URI。
    """
    import socket

    # 檢測是否在 localhost 執行
    is_localhost = False
    try:
        hostname = socket.gethostname()
        if hostname in ("localhost", "127.0.0.1", "::1"):
            is_localhost = True
        # 也檢查 Streamlit 內建 server 位址
        server_address = st.get_option("server.address") if hasattr(st, "get_option") else ""
        if server_address in ("localhost", "127.0.0.1", "0.0.0.0"):
            is_localhost = True
    except Exception:
        pass

    # 檢查是否可以從環境變數判斷
    if not is_localhost:
        try:
            import os
            streamlit_server = os.environ.get("STREAMLIT_SERVER_ADDRESS", "")
            if streamlit_server in ("localhost", "127.0.0.1"):
                is_localhost = True
        except Exception:
            pass

    if is_localhost:
        # 優先回傳 localhost URI
        for uri in allowed_uris:
            if "localhost" in uri or "127.0.0.1" in uri:
                return uri

    # 優先回傳非 localhost 的 URI（部署環境）
    for uri in allowed_uris:
        if "localhost" not in uri and "127.0.0.1" not in uri:
            return uri

    # 回退
    for uri in allowed_uris:
        if "localhost" in uri or "127.0.0.1" in uri:
            return uri

    return allowed_uris[0] if allowed_uris else "http://localhost:8501/oauth_callback"


# ── OAuth 輔助函式 ────────────────────────────────────────

def build_oauth_url(provider: str, client_id: str, redirect_uri: str) -> str:
    """建立 OAuth 授權 URL"""
    config = OAUTH_PROVIDERS.get(provider)
    if not config:
        return ""

    state = secrets_lib.token_urlsafe(32)
    st.session_state["oauth_state"] = state

    params = {
        "client_id": client_id,
        "redirect_uri": redirect_uri,
        "response_type": "code",
        "scope": config["scope"],
        "state": state,
        "access_type": "offline",
        "prompt": "consent",
    }

    if provider == "wechat":
        url = f"{config['authorize_url']}?appid={client_id}&redirect_uri={urllib.parse.quote(redirect_uri)}&response_type=code&scope={config['scope']}&state={state}#wechat_redirect"
        return url

    return f"{config['authorize_url']}?{urllib.parse.urlencode(params)}"


def _render_inline_oauth_buttons() -> None:
    """在登入頁面中直接繪製 OAuth 登入按鈕（無標題、無分隔線）

    用於登入 tab 頂部醒目位置，讓使用者可以直接使用第三方帳號登入。
    """
    provider_styles = {
        "google": {
            "name": "Google",
            "bg_color": "#4285F4",
            "icon": "G",
            "button_text": "使用 Google 帳號登入",
        },
        "facebook": {
            "name": "Facebook",
            "bg_color": "#1877F2",
            "icon": "f",
            "button_text": "使用 Facebook 帳號登入",
        },
        "wechat": {
            "name": "WeChat",
            "bg_color": "#07C160",
            "icon": "微",
            "button_text": "使用 WeChat 帳號登入",
        },
    }

    loaders = {
        "google": _load_google_oauth_config,
        "facebook": _load_facebook_oauth_config,
        "wechat": _load_wechat_oauth_config,
    }

    any_button_shown = False

    for provider_key, loader in loaders.items():
        config = loader()
        style = provider_styles[provider_key]

        if not config.get("enabled", True):
            continue

        if config["client_id"] and config["client_secret"]:
            any_button_shown = True
            redirect_uri = _get_redirect_uri(config["redirect_uris"])
            oauth_url = build_oauth_url(provider_key, config["client_id"], redirect_uri)

            st.markdown(
                f"""
                <a href="{oauth_url}" target="_self">
                    <button style="
                        background-color: {style['bg_color']}; color: white; border: none;
                        padding: 14px 28px; border-radius: 8px; cursor: pointer;
                        font-size: 17px; width: 100%; margin: 6px 0;
                        font-family: 'Google Sans', Roboto, sans-serif;
                        box-shadow: 0 2px 6px rgba(0,0,0,0.15);
                        transition: transform 0.1s ease;">
                        <span style="font-size: 22px; margin-right: 10px; font-weight: bold;">{style['icon']}</span>
                        {style['button_text']}
                    </button>
                </a>
                """,
                unsafe_allow_html=True,
            )

    if not any_button_shown:
        st.info(
            "💡 **第三方登入尚未設定**\n\n"
            "管理員可在後台「🔐 OAuth 整合」頁面設定 Google / Facebook / WeChat 登入。"
        )


def render_oauth_section() -> None:
    """繪製 OAuth 登入選項區塊（含標題與分隔線，用於獨立區塊）

    支援 Google、Facebook、WeChat 三種 OAuth 登入。
    管理員可透過後台 UI 啟用/停用各 provider 並設定 Client ID/Secret。
    """
    st.markdown("---")
    st.markdown("### 🌐 第三方登入")

    # Provider 按鈕樣式定義
    provider_styles = {
        "google": {
            "name": "Google",
            "bg_color": "#4285F4",
            "icon": "G",
            "button_text": "使用 Google 帳號登入",
        },
        "facebook": {
            "name": "Facebook",
            "bg_color": "#1877F2",
            "icon": "f",
            "button_text": "使用 Facebook 帳號登入",
        },
        "wechat": {
            "name": "WeChat",
            "bg_color": "#07C160",
            "icon": "微",
            "button_text": "使用 WeChat 帳號登入",
        },
    }

    loaders = {
        "google": _load_google_oauth_config,
        "facebook": _load_facebook_oauth_config,
        "wechat": _load_wechat_oauth_config,
    }

    any_button_shown = False

    for provider_key, loader in loaders.items():
        config = loader()
        style = provider_styles[provider_key]

        # 若管理員已停用此 provider
        if not config.get("enabled", True):
            continue

        if config["client_id"] and config["client_secret"]:
            any_button_shown = True
            redirect_uri = _get_redirect_uri(config["redirect_uris"])
            oauth_url = build_oauth_url(provider_key, config["client_id"], redirect_uri)

            st.markdown(
                f"""
                <a href="{oauth_url}" target="_self">
                    <button style="
                        background-color: {style['bg_color']}; color: white; border: none;
                        padding: 12px 24px; border-radius: 6px; cursor: pointer;
                        font-size: 16px; width: 100%; margin: 8px 0;
                        font-family: 'Google Sans', Roboto, sans-serif;">
                        <span style="font-size: 20px; margin-right: 8px;">{style['icon']}</span>
                        {style['button_text']}
                    </button>
                </a>
                """,
                unsafe_allow_html=True,
            )
            st.caption(f"🔗 Redirect URI：{redirect_uri}　|　來源：{config.get('source', '')}")

    if not any_button_shown:
        st.info(
            "💡 **第三方登入尚未設定**\n\n"
            "管理員可在後台「🔐 OAuth 整合」頁面設定 Google / Facebook / WeChat 登入。\n"
            "或將 `client_secret_*.json` 檔案放到專案根目錄（僅限 Google）。"
        )


def handle_oauth_callback() -> Optional[dict]:
    """處理 OAuth 回呼：從 URL query params 取得 authorization code，
    交換 access token，取得使用者資訊，建立或登入帳號。

    Returns:
        Optional[dict]: 登入成功時回傳使用者 dict，否則回傳 None
    """
    query_params = st.query_params
    code = query_params.get("code", None)
    state = query_params.get("state", None)

    if not code:
        return None

    # 驗證 state（防止 CSRF）
    saved_state = st.session_state.get("oauth_state")
    if saved_state and state != saved_state:
        st.error("⚠️ OAuth 安全驗證失敗（state 不符），請重新登入。")
        st.query_params.clear()
        return None

    # 嘗試處理 Google OAuth
    google_config = _load_google_oauth_config()
    if not google_config["client_id"] or not google_config["client_secret"]:
        st.info("🔧 OAuth 回呼已收到，但 Google OAuth 尚未設定。")
        st.query_params.clear()
        return None

    redirect_uri = _get_redirect_uri(google_config["redirect_uris"])

    try:
        # 交換 authorization code 為 access token
        token_response = _exchange_code_for_token(
            code,
            google_config["client_id"],
            google_config["client_secret"],
            redirect_uri,
        )

        if not token_response:
            st.error("❌ 無法取得 access token，請重新登入。")
            st.query_params.clear()
            return None

        access_token = token_response.get("access_token")
        if not access_token:
            st.error("❌ Token 回應中缺少 access_token。")
            st.query_params.clear()
            return None

        # 使用 access token 取得使用者資訊
        user_info = _fetch_google_userinfo(access_token)
        if not user_info:
            st.error("❌ 無法取得使用者資訊。")
            st.query_params.clear()
            return None

        google_id = user_info.get("sub", "")
        email = user_info.get("email", "")
        name = user_info.get("name", email.split("@")[0] if email else "google_user")

        # 查找或建立使用者帳號
        user = _find_or_create_oauth_user(
            oauth_provider="google",
            oauth_id=google_id,
            username=name,
            email=email,
        )

        if user:
            login_user(user)
            st.query_params.clear()
            st.success(f"歡迎，{name}！")
            st.rerun()
            return user
        else:
            st.error("❌ 無法建立或登入使用者帳號。")
            st.query_params.clear()
            return None

    except Exception as e:
        st.error(f"❌ OAuth 處理失敗：{str(e)}")
        st.query_params.clear()
        return None


def _exchange_code_for_token(
    code: str, client_id: str, client_secret: str, redirect_uri: str
) -> Optional[dict]:
    """使用 authorization code 向 Google 交換 access token

    Args:
        code: Google 回傳的 authorization code
        client_id: Google OAuth client ID
        client_secret: Google OAuth client secret
        redirect_uri: 必須與授權時使用的 redirect URI 完全一致

    Returns:
        Optional[dict]: token 回應 JSON，失敗時回傳 None
    """
    try:
        import requests
    except ImportError:
        st.error("請安裝 requests 套件：pip install requests")
        return None

    token_url = OAUTH_PROVIDERS["google"]["token_url"]

    payload = {
        "code": code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code",
    }

    try:
        resp = requests.post(token_url, data=payload, timeout=15)
        if resp.status_code == 200:
            return resp.json()
        else:
            st.error(f"Token 交換失敗（HTTP {resp.status_code}）：{resp.text[:200]}")
            return None
    except requests.RequestException as e:
        st.error(f"Token 交換網路錯誤：{str(e)}")
        return None


def _fetch_google_userinfo(access_token: str) -> Optional[dict]:
    """使用 access token 從 Google 取得使用者資訊

    Args:
        access_token: Google OAuth access token

    Returns:
        Optional[dict]: 使用者資訊 JSON，失敗時回傳 None
    """
    try:
        import requests
    except ImportError:
        return None

    userinfo_url = OAUTH_PROVIDERS["google"]["userinfo_url"]
    headers = {"Authorization": f"Bearer {access_token}"}

    try:
        resp = requests.get(userinfo_url, headers=headers, timeout=10)
        if resp.status_code == 200:
            return resp.json()
        else:
            return None
    except requests.RequestException:
        return None


def _find_or_create_oauth_user(
    oauth_provider: str,
    oauth_id: str,
    username: str,
    email: str,
) -> Optional[dict]:
    """查找現有的 OAuth 使用者，若不存在則建立新帳號

    Args:
        oauth_provider: OAuth 提供者名稱（如 "google"）
        oauth_id: 該提供者的唯一使用者 ID
        username: 使用者顯示名稱
        email: 電子郵件

    Returns:
        Optional[dict]: 使用者資料 dict
    """
    conn = get_connection()

    # 先用 oauth provider + id 查找
    row = conn.execute(
        "SELECT * FROM users WHERE oauth_provider = ? AND oauth_id = ?",
        (oauth_provider, oauth_id),
    ).fetchone()

    if row:
        conn.close()
        return dict(row)

    # 若不存在，建立新帳號
    # 確保 username 唯一（若有衝突則加後綴）
    base_username = username
    counter = 1
    while True:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if not existing:
            break
        username = f"{base_username}{counter}"
        counter += 1

    # 為 OAuth 使用者產生隨機密碼（不會直接使用）
    random_pw = secrets_lib.token_urlsafe(32)
    conn.execute(
        """
        INSERT INTO users (username, password_hash, email, oauth_provider, oauth_id, credits)
        VALUES (?, ?, ?, ?, ?, 100)
        """,
        (username, hash_password(random_pw), email, oauth_provider, oauth_id),
    )
    conn.commit()

    row = conn.execute(
        "SELECT * FROM users WHERE oauth_provider = ? AND oauth_id = ?",
        (oauth_provider, oauth_id),
    ).fetchone()
    conn.close()

    return dict(row) if row else None
