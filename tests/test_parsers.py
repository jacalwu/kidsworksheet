"""
單元測試：檔案解析模組（utils/parsers.py）

測試 PDF 與 Word (.docx) 檔案的文字擷取與結構化功能。
使用 mock 模擬外部依賴，不依賴實際安裝的套件。
"""

import os
import sys
import json
import unittest
from io import BytesIO
from unittest.mock import patch, MagicMock

# 將上層目錄加入 sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from utils.parsers import (
    parse_file,
    extract_pdf_text,
    extract_docx_text,
    format_parsed_content,
    get_parsed_json_for_display,
    get_pdf_page_count,
)


# ── 輔助函式：建立 Mock 模組 ──────────────────────────────

def _make_mock_pdfplumber(pages_data=None, side_effect=None):
    """建立 mock 的 pdfplumber 模組"""
    if side_effect:
        mock_module = MagicMock()
        mock_module.open = MagicMock(side_effect=side_effect)
        return mock_module

    if pages_data is None:
        # 預設：一個頁面，有文字
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "測試文字內容"
        mock_page.extract_tables.return_value = []
        pages_data = [mock_page]

    mock_pdf = MagicMock()
    mock_pdf.pages = pages_data
    mock_pdf.__enter__.return_value = mock_pdf
    mock_pdf.__exit__.return_value = False

    mock_module = MagicMock()
    mock_module.open.return_value = mock_pdf
    return mock_module


def _make_mock_docx(paragraphs_data=None, side_effect=None):
    """建立 mock 的 python-docx Document"""
    if side_effect:
        mock_module = MagicMock()
        mock_module.Document = MagicMock(side_effect=side_effect)
        return mock_module

    if paragraphs_data is None:
        para1 = MagicMock()
        para1.text = "第一章 介紹"
        para1.style.name = "Heading 1"
        para2 = MagicMock()
        para2.text = "這是一段內文。"
        para2.style.name = "Normal"
        paragraphs_data = [para1, para2]

    mock_doc = MagicMock()
    mock_doc.paragraphs = paragraphs_data

    mock_module = MagicMock()
    mock_module.Document = MagicMock(return_value=mock_doc)
    return mock_module


def _make_mock_pypdf2(pages_data=None):
    """建立 mock 的 PyPDF2.PdfReader"""
    if pages_data is None:
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "PyPDF2 擷取的文字"
        pages_data = [mock_page]

    mock_reader = MagicMock()
    mock_reader.pages = pages_data

    mock_module = MagicMock()
    mock_module.PdfReader = MagicMock(return_value=mock_reader)
    return mock_module


# ── PDF 解析測試 ──────────────────────────────────────────

class TestPDFParsing(unittest.TestCase):
    """PDF 解析功能測試"""

    def test_extract_pdf_with_pdfplumber(self):
        """測試使用 pdfplumber 解析 PDF"""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = "測試文字內容"
        mock_page.extract_tables.return_value = []

        mock_plumber = _make_mock_pdfplumber(pages_data=[mock_page])

        with patch.dict("sys.modules", {"pdfplumber": mock_plumber}):
            result = extract_pdf_text(b"dummy pdf content")

        self.assertIn("metadata", result)
        self.assertIn("content", result)
        self.assertEqual(result["metadata"]["file_type"], "pdf")
        self.assertGreaterEqual(len(result["content"]), 1)
        self.assertEqual(result["content"][0]["text"], "測試文字內容")

    def test_extract_pdf_with_tables(self):
        """測試 PDF 表格擷取"""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""
        mock_page.extract_tables.return_value = [
            [["姓名", "分數"], ["小明", "95"], ["小華", "87"]]
        ]

        mock_plumber = _make_mock_pdfplumber(pages_data=[mock_page])

        with patch.dict("sys.modules", {"pdfplumber": mock_plumber}):
            result = extract_pdf_text(b"dummy pdf with table")

        self.assertEqual(len(result["content"]), 1)
        self.assertGreater(len(result["content"][0]["tables"]), 0)
        self.assertEqual(result["content"][0]["tables"][0][0][0], "姓名")

    def test_extract_pdf_page_count(self):
        """測試 PDF 頁數計算"""
        mock_pages = []
        for i in range(5):
            p = MagicMock()
            p.extract_text.return_value = f"第 {i + 1} 頁內容"
            p.extract_tables.return_value = []
            mock_pages.append(p)

        mock_plumber = _make_mock_pdfplumber(pages_data=mock_pages)

        with patch.dict("sys.modules", {"pdfplumber": mock_plumber}):
            result = extract_pdf_text(b"five page pdf")

        self.assertEqual(result["metadata"]["pages"], 5)
        self.assertEqual(len(result["content"]), 5)

    def test_ocr_fallback_when_text_empty(self):
        """測試當頁面無文字時，OCR 模式的處理"""
        mock_page = MagicMock()
        mock_page.extract_text.return_value = ""  # 無文字
        mock_page.extract_tables.return_value = []

        mock_plumber = _make_mock_pdfplumber(pages_data=[mock_page])

        # 同時 mock pdf2image 和 pytesseract（OCR 依賴）
        with patch.dict("sys.modules", {
            "pdfplumber": mock_plumber,
            "pdf2image": MagicMock(),
            "pytesseract": MagicMock(),
        }):
            result = extract_pdf_text(b"image pdf", use_ocr=True)

        self.assertEqual(result["metadata"]["ocr_enabled"], True)
        self.assertIn("extraction_method", result["metadata"])

    def test_extract_pdf_with_pypdf2_fallback(self):
        """測試 pdfplumber 失敗時使用 PyPDF2 備援"""
        # pdfplumber 匯入失敗 → 觸發 PyPDF2 fallback
        mock_plumber = _make_mock_pdfplumber(side_effect=ImportError("No pdfplumber"))
        mock_pypdf2 = _make_mock_pypdf2()

        with patch.dict("sys.modules", {
            "pdfplumber": mock_plumber,
            "PyPDF2": mock_pypdf2,
        }):
            result = extract_pdf_text(b"test pdf bytes")

        self.assertIn("content", result)
        self.assertIn("metadata", result)

    def test_get_pdf_page_count(self):
        """測試取得 PDF 頁數"""
        mock_pages = [MagicMock() for _ in range(3)]
        mock_plumber = _make_mock_pdfplumber(pages_data=mock_pages)

        with patch.dict("sys.modules", {"pdfplumber": mock_plumber}):
            count = get_pdf_page_count(b"three pages")
            self.assertEqual(count, 3)

    def test_extract_pdf_both_fail(self):
        """測試 pdfplumber 與 PyPDF2 都失敗的情況"""
        mock_plumber = _make_mock_pdfplumber(side_effect=ImportError("No pdfplumber"))
        mock_pypdf2 = MagicMock()
        mock_pypdf2.PdfReader = MagicMock(side_effect=Exception("Parse error"))

        with patch.dict("sys.modules", {
            "pdfplumber": mock_plumber,
            "PyPDF2": mock_pypdf2,
        }):
            result = extract_pdf_text(b"corrupted pdf")

        self.assertIn("metadata", result)
        self.assertIn("error", result["metadata"])


# ── Word 解析測試 ─────────────────────────────────────────

class TestDocxParsing(unittest.TestCase):
    """Word (.docx) 解析功能測試"""

    def test_extract_docx_basic(self):
        """測試基本 Word 文字擷取"""
        para1 = MagicMock()
        para1.text = "第一章 介紹"
        para1.style.name = "Heading 1"

        para2 = MagicMock()
        para2.text = "這是一段內文。"
        para2.style.name = "Normal"

        para3 = MagicMock()
        para3.text = "這是第二段內文。"
        para3.style.name = "Normal"

        mock_docx = _make_mock_docx(paragraphs_data=[para1, para2, para3])

        with patch.dict("sys.modules", {"docx": mock_docx}):
            result = extract_docx_text(b"dummy docx content")

        self.assertIn("metadata", result)
        self.assertIn("content", result)
        self.assertEqual(result["metadata"]["file_type"], "docx")
        self.assertGreater(len(result["content"]), 0)

    def test_extract_docx_multiple_headings(self):
        """測試多層標題結構"""
        para1 = MagicMock()
        para1.text = "大標題"
        para1.style.name = "Heading 1"

        para2 = MagicMock()
        para2.text = "副標題"
        para2.style.name = "Heading 2"

        para3 = MagicMock()
        para3.text = "內文段落"
        para3.style.name = "Normal"

        mock_docx = _make_mock_docx(paragraphs_data=[para1, para2, para3])

        with patch.dict("sys.modules", {"docx": mock_docx}):
            result = extract_docx_text(b"docx with headings")

        sections = result["content"]
        self.assertGreaterEqual(len(sections), 1)

        headings = [s["heading"] for s in sections if s["heading"]]
        self.assertIn("大標題", headings)

    def test_extract_docx_no_headings(self):
        """測試無標題的純文字文件"""
        paragraphs = []
        for i in range(5):
            p = MagicMock()
            p.text = f"段落 {i + 1} 的內容"
            p.style.name = "Normal"
            paragraphs.append(p)

        mock_docx = _make_mock_docx(paragraphs_data=paragraphs)

        with patch.dict("sys.modules", {"docx": mock_docx}):
            result = extract_docx_text(b"flat docx")

        self.assertGreater(len(result["content"]), 0)
        total = sum(len(s.get("paragraphs", [])) for s in result["content"])
        self.assertGreater(total, 0)

    def test_extract_docx_empty(self):
        """測試空白文件"""
        mock_docx = _make_mock_docx(paragraphs_data=[])

        with patch.dict("sys.modules", {"docx": mock_docx}):
            result = extract_docx_text(b"empty docx")

        self.assertEqual(result["metadata"]["file_type"], "docx")
        self.assertEqual(len(result["content"]), 0)

    def test_extract_docx_error_handling(self):
        """測試 docx 解析錯誤處理"""
        mock_docx = _make_mock_docx(side_effect=Exception("解析失敗"))

        with patch.dict("sys.modules", {"docx": mock_docx}):
            result = extract_docx_text(b"corrupted docx")

        self.assertIn("error", result["metadata"])
        self.assertEqual(result["metadata"]["extraction_method"], "failed")


# ── 整合解析介面測試 ──────────────────────────────────────

class TestParseFile(unittest.TestCase):
    """整合解析介面測試"""

    def test_parse_pdf_file(self):
        """測試依副檔名自動選擇 PDF 解析器"""
        with patch("utils.parsers.extract_pdf_text") as mock_extract:
            mock_extract.return_value = {
                "metadata": {"file_type": "pdf"},
                "content": [{"page_number": 1, "text": "test"}],
            }

            result = parse_file(b"content", "test.pdf")
            self.assertEqual(result["metadata"]["file_type"], "pdf")
            mock_extract.assert_called_once()

    def test_parse_docx_file(self):
        """測試依副檔名自動選擇 Word 解析器"""
        with patch("utils.parsers.extract_docx_text") as mock_extract:
            mock_extract.return_value = {
                "metadata": {"file_type": "docx"},
                "content": [{"heading": "Test", "paragraphs": ["content"]}],
            }

            result = parse_file(b"content", "test.docx")
            self.assertEqual(result["metadata"]["file_type"], "docx")
            mock_extract.assert_called_once()

    def test_parse_unsupported_file_type(self):
        """測試不支援的檔案類型"""
        result = parse_file(b"content", "test.txt")
        self.assertIn("error", result["metadata"])
        self.assertEqual(len(result["content"]), 0)

    def test_parse_file_adds_metadata(self):
        """測試 parse_file 會自動加入檔案層級 metadata"""
        with patch("utils.parsers.extract_pdf_text") as mock_extract:
            mock_extract.return_value = {
                "metadata": {},
                "content": [],
            }

            result = parse_file(b"1234567890", "homework.pdf")
            self.assertIn("file_name", result["metadata"])
            self.assertEqual(result["metadata"]["file_name"], "homework.pdf")
            self.assertIn("file_size_bytes", result["metadata"])
            self.assertEqual(result["metadata"]["file_size_bytes"], 10)
            self.assertIn("file_hash", result["metadata"])

    def test_parse_doc_file_as_docx(self):
        """測試 .doc 副檔名也被視為 Word 文件"""
        with patch("utils.parsers.extract_docx_text") as mock_extract:
            mock_extract.return_value = {
                "metadata": {"file_type": "docx"},
                "content": [],
            }

            result = parse_file(b"content", "test.doc")
            self.assertEqual(result["metadata"]["file_type"], "docx")


# ── 格式化函式測試 ────────────────────────────────────────

class TestFormatFunctions(unittest.TestCase):
    """格式化函式測試"""

    def test_format_parsed_content_pdf(self):
        """測試 PDF 解析結果格式化"""
        parsed = {
            "metadata": {"file_name": "test.pdf"},
            "content": [
                {
                    "page_number": 1,
                    "text": "第一頁內容",
                    "tables": [],
                    "ocr_text": "",
                },
                {
                    "page_number": 2,
                    "text": "第二頁內容",
                    "tables": [[["A", "B"], ["1", "2"]]],
                    "ocr_text": "",
                },
            ],
        }

        formatted = format_parsed_content(parsed)

        self.assertIn("test.pdf", formatted)
        self.assertIn("第一頁內容", formatted)
        self.assertIn("第二頁內容", formatted)
        self.assertIn("第 1 頁", formatted)
        self.assertIn("第 2 頁", formatted)
        self.assertIn("A | B", formatted)  # 表格內容

    def test_format_parsed_content_docx(self):
        """測試 Word 解析結果格式化"""
        parsed = {
            "metadata": {"file_name": "notes.docx"},
            "content": [
                {
                    "heading": "第一章",
                    "heading_level": 1,
                    "paragraphs": ["段落 A", "段落 B"],
                },
                {
                    "heading": "第二章",
                    "heading_level": 1,
                    "paragraphs": ["段落 C"],
                },
            ],
        }

        formatted = format_parsed_content(parsed)

        self.assertIn("notes.docx", formatted)
        self.assertIn("第一章", formatted)
        self.assertIn("段落 A", formatted)
        self.assertIn("段落 B", formatted)

    def test_format_parsed_content_with_ocr(self):
        """測試包含 OCR 文字的格式化輸出"""
        parsed = {
            "metadata": {"file_name": "scan.pdf"},
            "content": [
                {
                    "page_number": 1,
                    "text": "",
                    "tables": [],
                    "ocr_text": "OCR 辨識文字",
                },
            ],
        }

        formatted = format_parsed_content(parsed)
        self.assertIn("OCR 辨識文字", formatted)

    def test_get_parsed_json_for_display(self):
        """測試 JSON 顯示格式輸出"""
        parsed = {
            "metadata": {"file_type": "pdf", "pages": 3},
            "content": [
                {"page_number": 1, "text": "a" * 100, "tables": [], "ocr_text": ""},
                {"page_number": 2, "text": "b" * 50, "tables": [[["x"]]], "ocr_text": ""},
            ],
        }

        display = get_parsed_json_for_display(parsed)
        data = json.loads(display)

        self.assertIn("metadata", data)
        self.assertIn("content_summary", data)
        self.assertEqual(len(data["content_summary"]), 2)
        self.assertEqual(data["content_summary"][0]["text_length"], 100)
        self.assertEqual(data["content_summary"][1]["table_count"], 1)


if __name__ == "__main__":
    unittest.main()
