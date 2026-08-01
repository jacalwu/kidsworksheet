# 📚 AI 學習助手

使用 AI 將 PDF / Word 復習資料自動轉換為練習題（Worksheet）與模擬考試卷。

🌐 **Demo（Streamlit Cloud）**：部署後可於 https://share.streamlit.io/ 使用

---

## ✨ 功能特色

- 🔐 **多種登入方式**：支援本地帳號密碼 / Google OAuth / Facebook OAuth / WeChat OAuth
- 👶 **Kid 管理**：可新增/編輯/刪除多位孩子，並為每位選擇年級
- 📤 **檔案上傳**：支援 PDF（含多頁、含圖片）與 Word (.docx) 格式
- 🔍 **智慧解析**：自動擷取檔案內容，結構化為 JSON（含 metadata、段落、頁數）
- 🖼️ **OCR 支援**：可選用 OCR 辨識 PDF 中的圖片文字（需安裝 Tesseract + Poppler）
- 📝 **練習題生成**：使用 DeepSeek LLM 生成包含選擇/填充/簡答的練習題
- 📋 **模擬考試卷**：生成正式考試卷，含配分、評分標準與参考答案
- 🌐 **網路搜尋**：可選用 Web Search 補充相關資料，豐富題目內容
- 📥 **Word 下載**：生成結果可直接下載為 .docx 格式
- 💯 **配額管理**：每位使用者 100 次免費生成，管理員可調整配額
- 🛠️ **管理員控制台**：查看所有使用者、調整配額、匯出 CSV
- 🔧 **Mock 模式**：不需 API Key 即可在本地測試完整流程

---

## 🚀 快速開始

### 1. 安裝依賴

```bash
# 複製專案
git clone <your-repo-url>
cd homework

# 安裝 Python 依賴
pip install -r requirements.txt
```

### 2. 設定 config.toml

```bash
# 複製範例設定檔
cp config.toml.example config.toml

# 編輯 config.toml（使用文字編輯器）
# 基本設定保留 LEARNING_DEPLOYMENT = "local" 即可在 Mock 模式下測試
```

### 3. 啟動應用程式

```bash
streamlit run streamlit_app.py
```

瀏覽器開啟 http://localhost:8501 即可使用。

**預設管理員帳號**：`jacalwu` / `jacalwu123456`（首次登入後請立即修改密碼）

---

## 📁 專案結構

```
.
├── streamlit_app.py          # 主應用程式入口
├── config.toml.example       # 設定檔範例
├── requirements.txt          # Python 依賴
├── README.md                 # 本文件
├── Dockerfile                # Docker 部署設定
├── utils/
│   ├── __init__.py
│   ├── database.py           # 資料庫模組（SQLite）
│   ├── auth.py               # 認證模組（本地 + OAuth）
│   ├── parsers.py            # 檔案解析模組（PDF / Word）
│   ├── generator.py          # 題目生成模組（LLM + Web Search）
│   └── admin.py              # 管理員模組
└── tests/
    ├── __init__.py
    └── test_parsers.py       # 解析器單元測試
```

---

## ⚙️ 設定說明

所有設定從 `config.toml` 檔案讀取（部署時使用 `.streamlit/secrets.toml`）：

| 設定項 | 說明 | 預設值 |
|---|---|---|
| `LEARNING_DEPLOYMENT` | 部署模式：`"local"`（Mock）或 `"cloud"`（真實 API） | `"local"` |
| `LEARNING_API_KEY` | DeepSeek API Key | （空白） |
| `LEARNING_LLM_MODEL` | LLM 模型名稱 | `"deepseek-chat"` |
| `LEARNING_LLM_URL` | LLM API 端點 | `"https://api.deepseek.com/v1"` |
| `LEARNING_WEB_SEARCH_API_KEY` | Web Search API Key | （空白） |
| `LEARNING_WEB_SEARCH_ENGINE` | 搜尋引擎：`"serpapi"` 或 `"bing"` | `"serpapi"` |
| `LEARNING_ADMIN_USERNAME` | 管理員帳號 | `"jacalwu"` |
| `LEARNING_ADMIN_PASSWORD` | 管理員預設密碼 | `"jacalwu123456"` |
| `LEARNING_DEFAULT_CREDITS` | 新使用者預設配額 | `100` |

---

## 🔐 OAuth 設定

### Google OAuth（建議用於本地測試）

1. 前往 [Google Cloud Console](https://console.cloud.google.com/)
2. 建立專案 → API 和服務 → 憑證 → 建立 OAuth 2.0 用戶端 ID
3. 應用程式類型選擇「網頁應用程式」
4. 已授權的重新導向 URI 加入：`http://localhost:8501/oauth_callback`
5. 將取得的 `Client ID` 與 `Client Secret` 寫入 `config.toml`：
   ```toml
   GOOGLE_CLIENT_ID = "your-client-id.apps.googleusercontent.com"
   GOOGLE_CLIENT_SECRET = "your-client-secret"
   ```

### Facebook OAuth

1. 前往 [Facebook Developers](https://developers.facebook.com/)
2. 建立應用程式 → 選擇「消費者」類型
3. 在 Facebook 登入 → 設定中，加入有效的 OAuth 重新導向 URI
4. 將取得的 App ID 與 App Secret 寫入 `config.toml`

### WeChat OAuth

⚠️ **限制說明**：
- WeChat OAuth 需要微信開放平台帳號（需中國大陸企業營業執照）
- 回呼 URL 必須是已備案的網域名稱
- 個人開發者與海外使用者**無法使用**
- 替代方案：使用本地帳號密碼登入，或整合其他 OAuth 提供者

### Streamlit Cloud 上的 OAuth 限制

Streamlit Cloud 為每個 App 分配動態子網域（例如 `your-app.streamlit.app`），
且可能因部署更新而變更。這對於需要固定 redirect URI 的 OAuth 提供者是個限制。

**建議做法**：
1. **主要使用本地帳號密碼登入**（無需 OAuth，在任何環境都能運作）
2. 若有自有網域，可在 Streamlit Cloud 設定自訂網域後再設定 OAuth
3. 本地測試時使用 `localhost:8501` 作為 redirect URI

---

## 🔧 Mock 模式 vs 雲端模式

### Mock 模式（`LEARNING_DEPLOYMENT = "local"`）

- ✅ 不需任何 API Key
- ✅ 產生內建範例題目內容
- ✅ 適合開發測試、展示功能流程
- ❌ 題目內容與上傳檔案無關

### 雲端模式（`LEARNING_DEPLOYMENT = "cloud"`）

- ✅ 使用真實 DeepSeek LLM 根據檔案內容生成題目
- ✅ 可使用 Web Search 補充資料
- ❌ 需要有效的 API Key
- ❌ 每次生成消耗 API 費用

---

## 🧪 執行測試

```bash
# 執行所有測試
python -m pytest tests/ -v

# 僅執行解析器測試
python -m pytest tests/test_parsers.py -v
```

---

## 🐳 Docker 部署

```bash
# 建置映像檔
docker build -t ai-learning-assistant .

# 啟動容器
docker run -p 8501:8501 \
  -v $(pwd)/config.toml:/app/config.toml \
  -v $(pwd)/learning_app.db:/app/learning_app.db \
  ai-learning-assistant
```

---

## 📤 部署到 Streamlit Cloud

1. 將專案推送到 GitHub 公開或私有倉庫
2. 前往 https://share.streamlit.io/
3. 點擊「New app」→ 選擇你的倉庫、分支與主檔案（`streamlit_app.py`）
4. 在「Advanced settings」中設定 Secrets（貼上 `config.toml` 的內容）
5. 點擊「Deploy」即可

⚠️ **注意**：
- Streamlit Cloud 的檔案系統是暫時性的，重啟後會還原。已上傳的檔案會遺失。
- SQLite 資料庫在 Streamlit Cloud 上可正常運作，但免費方案有資源限制。
- 若需持久化儲存，建議整合外部資料庫（如 Supabase、PlanetScale）。

---

## 🖼️ OCR 功能設定（選用）

OCR 功能需要額外安裝系統套件：

### Windows
1. 下載並安裝 [Tesseract OCR](https://github.com/UB-Mannheim/tesseract/wiki)（請選擇含中文語言的版本）
2. 下載 [Poppler for Windows](https://github.com/oschwartz10612/poppler-windows/releases)
3. 將兩者的 `bin` 目錄加入系統 PATH
4. 安裝 Python 套件：`pip install pytesseract pdf2image`

### macOS
```bash
brew install tesseract tesseract-lang poppler
pip install pytesseract pdf2image
```

### Ubuntu / Debian
```bash
sudo apt install tesseract-ocr tesseract-ocr-chi-tra poppler-utils
pip install pytesseract pdf2image
```

---

## ⚠️ 常見問題

**Q：上傳 PDF 後無法解析文字？**
A：若 PDF 為掃描圖片（無文字層），請啟用「OCR 掃描」選項。需先安裝 Tesseract 與 Poppler。

**Q：生成按鈕無法點擊？**
A：請確認：1) 已新增至少一位 Kid 2) 已上傳並解析檔案（或在「直接貼上文字」模式中輸入內容）3) 配額尚未用盡。

**Q：如何取得 DeepSeek API Key？**
A：前往 https://platform.deepseek.com 註冊帳號並取得 API Key。

**Q：管理員密碼忘記了怎麼辦？**
A：直接修改 SQLite 資料庫中的 `users` 表，或刪除 `learning_app.db` 檔案重新初始化（會遺失所有資料）。

---

## 📄 授權

本專案僅供教育與學習用途。
