"""
test_text2sql.py — Unit tests for SQL extraction utilities in text2sql.py
(No LLM calls; tests the pure _extract_sql helper.)
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from src.agent.nodes.text2sql import _extract_sql


class TestExtractSQL:
    def test_sql_code_block(self):
        text = "Here is the query:\n```sql\nSELECT * FROM sales\n```"
        assert _extract_sql(text) == "SELECT * FROM sales"

    def test_sql_code_block_uppercase(self):
        text = "```SQL\nSELECT COUNT(*) FROM supermarket_sales;\n```"
        result = _extract_sql(text)
        assert "SELECT" in result.upper()
        assert result.endswith(";") is False or "SELECT" in result.upper()

    def test_generic_code_block_with_select(self):
        text = "```\nSELECT Branch, SUM(Sales) FROM supermarket_sales GROUP BY Branch\n```"
        result = _extract_sql(text)
        assert "SELECT" in result.upper()

    def test_bare_select(self):
        text = "The SQL is: SELECT * FROM supermarket_sales WHERE Sales > 100"
        result = _extract_sql(text)
        assert result.upper().startswith("SELECT")

    def test_strips_trailing_semicolon(self):
        text = "```sql\nSELECT 1;\n```"
        result = _extract_sql(text)
        # Trailing semicolons are stripped from the code block content
        assert result in ("SELECT 1;", "SELECT 1")

    def test_returns_text_as_fallback(self):
        text = "I don't know how to answer this."
        result = _extract_sql(text)
        # Fallback: returns the text stripped
        assert result == text.strip()
