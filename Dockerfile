# ═══════════════════════════════════════════════════════════
# AI 學習助手 — Dockerfile
# ═══════════════════════════════════════════════════════════
# 建置與執行：
#   docker build -t ai-learning-assistant .
#   docker run -p 8501:8501 ai-learning-assistant
# ═══════════════════════════════════════════════════════════

FROM python:3.11-slim

# 設定工作目錄
WORKDIR /app

# 安裝系統依賴（可選：OCR 支援）
RUN apt-get update && apt-get install -y --no-install-recommends \
    tesseract-ocr \
    tesseract-ocr-chi-tra \
    tesseract-ocr-chi-sim \
    poppler-utils \
    && rm -rf /var/lib/apt/lists/*

# 複製依賴檔案
COPY requirements.txt .

# 安裝 Python 依賴
RUN pip install --no-cache-dir -r requirements.txt

# 安裝 OCR 相關 Python 套件
RUN pip install --no-cache-dir pytesseract pdf2image

# 複製專案檔案
COPY . .

# 建立上傳目錄
RUN mkdir -p uploads

# 暴露 Streamlit 預設埠
EXPOSE 8501

# 健康檢查
HEALTHCHECK CMD curl --fail http://localhost:8501/_stcore/health || exit 1

# 啟動應用程式
ENTRYPOINT ["streamlit", "run", "streamlit_app.py", "--server.port=8501", "--server.address=0.0.0.0"]
