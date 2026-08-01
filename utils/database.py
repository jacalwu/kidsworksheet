"""
資料庫模組：管理使用者、Kid、上傳紀錄、使用紀錄與配額。
使用 SQLite 作為後端儲存，適用於 Streamlit Cloud 部署。
"""

import sqlite3
import os
import hashlib
import secrets
from datetime import datetime, timezone
from typing import Optional, Any

# 資料庫連線路徑（由 config 設定，預設為專案根目錄下的 learning_app.db）
DB_PATH: str = "learning_app.db"


def get_db_path() -> str:
    """取得資料庫檔案路徑"""
    return DB_PATH


def set_db_path(path: str) -> None:
    """設定資料庫檔案路徑"""
    global DB_PATH
    DB_PATH = path


def get_connection() -> sqlite3.Connection:
    """建立並回傳資料庫連線"""
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def init_db() -> None:
    """初始化資料庫表格結構"""
    conn = get_connection()
    cursor = conn.cursor()

    # 使用者資料表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            email TEXT,
            oauth_provider TEXT,
            oauth_id TEXT,
            credits INTEGER DEFAULT 100,
            is_admin INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Kid 資料表
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS kids (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            grade TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 上傳檔案紀錄
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS uploaded_files (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kid_id INTEGER,
            file_name TEXT NOT NULL,
            file_type TEXT NOT NULL,
            page_count INTEGER DEFAULT 0,
            parsed_json TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 使用紀錄（生成 worksheet/exam）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usage_records (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            kid_id INTEGER,
            type TEXT NOT NULL,
            file_name TEXT,
            credits_used INTEGER DEFAULT 1,
            token_usage TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
        )
    """)

    # 為既有資料庫補加 token_usage 欄位（若不存在）
    try:
        cursor.execute("ALTER TABLE usage_records ADD COLUMN token_usage TEXT")
    except Exception:
        pass  # 欄位已存在

    # 應用程式設定（管理員可透過 UI 修改 LLM 參數）
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS app_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL,
            updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()
    conn.close()


# ── 應用程式設定 CRUD ─────────────────────────────────────

def get_all_settings() -> dict:
    """從資料庫讀取全部應用程式設定，回傳 dict"""
    conn = get_connection()
    rows = conn.execute("SELECT key, value FROM app_settings").fetchall()
    conn.close()
    return {row["key"]: row["value"] for row in rows}


def get_setting(key: str, default: str = "") -> str:
    """讀取單一應用程式設定值

    Args:
        key: 設定鍵名
        default: 若無此設定時的回退值

    Returns:
        str: 設定值
    """
    conn = get_connection()
    row = conn.execute(
        "SELECT value FROM app_settings WHERE key = ?", (key,)
    ).fetchone()
    conn.close()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    """寫入或更新應用程式設定（UPSERT）

    Args:
        key: 設定鍵名
        value: 設定值
    """
    conn = get_connection()
    conn.execute(
        """
        INSERT INTO app_settings (key, value, updated_at)
        VALUES (?, ?, CURRENT_TIMESTAMP)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value, updated_at = CURRENT_TIMESTAMP
        """,
        (key, value),
    )
    conn.commit()
    conn.close()


def delete_setting(key: str) -> None:
    """刪除單一應用程式設定（讓它回退到 config.toml / 預設值）

    Args:
        key: 設定鍵名
    """
    conn = get_connection()
    conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    conn.commit()
    conn.close()


# ── 密碼工具 ──────────────────────────────────────────────

def hash_password(password: str) -> str:
    """使用 SHA-256 + salt 雜湊密碼"""
    salt = secrets.token_hex(16)
    h = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
    return f"{salt}${h}"


def verify_password(password: str, password_hash: str) -> bool:
    """驗證密碼是否與雜湊值匹配"""
    try:
        salt, h = password_hash.split("$", 1)
        expected = hashlib.sha256((password + salt).encode("utf-8")).hexdigest()
        return h == expected
    except (ValueError, AttributeError):
        return False


# ── 使用者 CRUD ───────────────────────────────────────────

def create_user(username: str, password: str, email: str = "",
                is_admin: int = 0, credits: int = 100) -> Optional[int]:
    """建立新使用者，回傳 user_id 或 None（若帳號已存在）"""
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO users (username, password_hash, email, is_admin, credits) VALUES (?, ?, ?, ?, ?)",
            (username, hash_password(password), email, is_admin, credits),
        )
        conn.commit()
        return cursor.lastrowid
    except sqlite3.IntegrityError:
        return None
    finally:
        conn.close()


def get_user_by_username(username: str) -> Optional[sqlite3.Row]:
    """依使用者名稱查詢使用者"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
    conn.close()
    return row


def get_user_by_id(user_id: int) -> Optional[sqlite3.Row]:
    """依 ID 查詢使用者"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM users WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    return row


def authenticate_user(username: str, password: str) -> Optional[sqlite3.Row]:
    """驗證使用者登入，成功回傳 user row，失敗回傳 None"""
    user = get_user_by_username(username)
    if user and verify_password(password, user["password_hash"]):
        return user
    return None


def update_user_password(user_id: int, new_password: str) -> bool:
    """更新使用者密碼"""
    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (hash_password(new_password), user_id),
    )
    conn.commit()
    conn.close()
    return True


def update_user_credits(user_id: int, credits: int) -> bool:
    """更新使用者剩餘配額"""
    conn = get_connection()
    conn.execute("UPDATE users SET credits = ? WHERE id = ?", (credits, user_id))
    conn.commit()
    conn.close()
    return True


def deduct_credit(user_id: int) -> bool:
    """扣除 1 點配額，若配額不足則回傳 False"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT credits FROM users WHERE id = ?", (user_id,))
    row = cursor.fetchone()
    if row and row["credits"] > 0:
        cursor.execute(
            "UPDATE users SET credits = credits - 1 WHERE id = ?", (user_id,)
        )
        conn.commit()
        conn.close()
        return True
    conn.close()
    return False


def get_all_users() -> list[dict]:
    """取得所有使用者（管理員用），回傳 dict 列表以支援 .get() 操作"""
    conn = get_connection()
    rows = conn.execute("SELECT * FROM users ORDER BY id").fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ── Kid CRUD ──────────────────────────────────────────────

def create_kid(user_id: int, name: str, grade: str) -> int:
    """新增 Kid，回傳 kid_id"""
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO kids (user_id, name, grade) VALUES (?, ?, ?)",
        (user_id, name, grade),
    )
    conn.commit()
    kid_id = cursor.lastrowid
    conn.close()
    return kid_id


def get_kids_by_user(user_id: int) -> list[sqlite3.Row]:
    """取得使用者的所有 Kid"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM kids WHERE user_id = ? ORDER BY id", (user_id,)
    ).fetchall()
    conn.close()
    return rows


def get_kid_by_id(kid_id: int) -> Optional[sqlite3.Row]:
    """依 ID 查詢 Kid"""
    conn = get_connection()
    row = conn.execute("SELECT * FROM kids WHERE id = ?", (kid_id,)).fetchone()
    conn.close()
    return row


def update_kid(kid_id: int, name: str, grade: str) -> bool:
    """更新 Kid 資訊"""
    conn = get_connection()
    conn.execute(
        "UPDATE kids SET name = ?, grade = ? WHERE id = ?", (name, grade, kid_id)
    )
    conn.commit()
    conn.close()
    return True


def delete_kid(kid_id: int) -> bool:
    """刪除 Kid"""
    conn = get_connection()
    conn.execute("DELETE FROM kids WHERE id = ?", (kid_id,))
    conn.commit()
    conn.close()
    return True


# ── 上傳檔案紀錄 ──────────────────────────────────────────

def save_uploaded_file_record(
    user_id: int,
    file_name: str,
    file_type: str,
    kid_id: Optional[int] = None,
    page_count: int = 0,
    parsed_json: Optional[str] = None,
) -> int:
    """儲存上傳檔案紀錄（同名檔案會覆蓋舊紀錄，只保留最新）

    Args:
        user_id: 使用者 ID
        file_name: 檔案名稱
        file_type: 檔案類型（pdf/docx/doc）
        kid_id: 關聯的 Kid ID
        page_count: 頁數
        parsed_json: 解析後的 JSON 內容

    Returns:
        int: 紀錄 ID
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 檢查是否已有同名檔案
    existing = cursor.execute(
        "SELECT id FROM uploaded_files WHERE user_id = ? AND file_name = ?",
        (user_id, file_name),
    ).fetchone()

    if existing:
        # 覆蓋舊紀錄
        cursor.execute(
            """
            UPDATE uploaded_files
            SET kid_id = ?, file_type = ?, page_count = ?, parsed_json = ?,
                created_at = CURRENT_TIMESTAMP
            WHERE id = ?
            """,
            (kid_id, file_type, page_count, parsed_json, existing["id"]),
        )
        conn.commit()
        record_id = existing["id"]
    else:
        # 新增紀錄
        cursor.execute(
            "INSERT INTO uploaded_files (user_id, kid_id, file_name, file_type, page_count, parsed_json) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, kid_id, file_name, file_type, page_count, parsed_json),
        )
        conn.commit()
        record_id = cursor.lastrowid

    conn.close()
    return record_id


def get_uploaded_files_by_user(user_id: int) -> list[dict]:
    """取得使用者的上傳紀錄，回傳 dict 列表以支援 .get() 操作"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM uploaded_files WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ── 使用紀錄 ──────────────────────────────────────────────

def record_usage(
    user_id: int,
    usage_type: str,
    kid_id: Optional[int] = None,
    file_name: Optional[str] = None,
    credits_used: int = 1,
    token_usage: Optional[str] = None,
) -> int:
    """記錄一次使用（生成 worksheet/exam），回傳 record_id

    Args:
        user_id: 使用者 ID
        usage_type: 類型（worksheet / exam）
        kid_id: Kid ID
        file_name: 使用的檔案名稱
        credits_used: 消耗配額
        token_usage: Token 用量的 JSON 字串（選填）
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO usage_records (user_id, kid_id, type, file_name, credits_used, token_usage) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (user_id, kid_id, usage_type, file_name, credits_used, token_usage),
    )
    conn.commit()
    record_id = cursor.lastrowid
    conn.close()
    return record_id


def get_usage_records_by_user(user_id: int) -> list[sqlite3.Row]:
    """取得使用者的使用紀錄"""
    conn = get_connection()
    rows = conn.execute(
        "SELECT * FROM usage_records WHERE user_id = ? ORDER BY created_at DESC",
        (user_id,),
    ).fetchall()
    conn.close()
    return rows


def get_all_usage_records() -> list[dict]:
    """取得所有使用紀錄（管理員用），回傳 dict 列表以支援 .get() 操作"""
    conn = get_connection()
    rows = conn.execute(
        """
        SELECT ur.*, u.username
        FROM usage_records ur
        JOIN users u ON ur.user_id = u.id
        ORDER BY ur.created_at DESC
        """
    ).fetchall()
    conn.close()
    return [dict(row) for row in rows]


# ── 管理員初始化 ──────────────────────────────────────────

def ensure_admin_user(admin_username: str, admin_password: str) -> None:
    """確保管理員帳號存在；若不存在則建立，若存在且為預設密碼則提示更新"""
    conn = get_connection()
    existing = conn.execute(
        "SELECT * FROM users WHERE username = ?", (admin_username,)
    ).fetchone()
    if existing is None:
        conn.execute(
            "INSERT INTO users (username, password_hash, email, is_admin, credits) "
            "VALUES (?, ?, ?, 1, 999999)",
            (admin_username, hash_password(admin_password), ""),
        )
        conn.commit()
    conn.close()
