"""
test_sql_validator.py — Unit tests for sql_validator.validate_sql()
"""
import os
import sqlite3
import tempfile

import pytest

# Make sure src/ is importable
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

from src.agent.nodes.sql_validator import validate_sql, MAX_RETRIES


@pytest.fixture
def tmp_db(tmp_path):
    """Create a tiny SQLite DB with a test table."""
    db_path = str(tmp_path / "test.db")
    conn = sqlite3.connect(db_path)
    conn.execute(
        "CREATE TABLE supermarket_sales (Branch TEXT, Sales REAL, Date TEXT)"
    )
    conn.execute("INSERT INTO supermarket_sales VALUES ('Alex', 500.0, '2019-01-05')")
    conn.commit()
    conn.close()
    return db_path


class TestSafeQueries:
    """
    SELECT / WHERE / GROUP BY / 結尾分號 → 應通過
    """
    def test_simple_select(self, tmp_db):
        ok, err = validate_sql("SELECT * FROM supermarket_sales", tmp_db)
        assert ok, err

    def test_select_with_where(self, tmp_db):
        ok, err = validate_sql(
            "SELECT Branch, Sales FROM supermarket_sales WHERE Sales > 100", tmp_db
        )
        assert ok, err

    def test_select_aggregate(self, tmp_db):
        ok, err = validate_sql(
            "SELECT Branch, SUM(Sales) FROM supermarket_sales GROUP BY Branch", tmp_db
        )
        assert ok, err

    def test_trailing_semicolon_ok(self, tmp_db):
        ok, err = validate_sql("SELECT COUNT(*) FROM supermarket_sales;", tmp_db)
        assert ok, err


class TestDangerousQueries:
    """
    INSERT / DELETE / DROP / UPDATE / 多語句 / 空字串 → 應被阻擋
    """
    def test_insert_blocked(self, tmp_db):
        ok, err = validate_sql(
            "INSERT INTO supermarket_sales VALUES ('B', 1.0, '2019-01-01')", tmp_db
        )
        assert not ok
        assert "INSERT" in err.upper() or "SELECT" in err.upper()

    def test_delete_blocked(self, tmp_db):
        ok, err = validate_sql("DELETE FROM supermarket_sales", tmp_db)
        assert not ok

    def test_drop_blocked(self, tmp_db):
        ok, err = validate_sql("DROP TABLE supermarket_sales", tmp_db)
        assert not ok

    def test_update_blocked(self, tmp_db):
        ok, err = validate_sql("UPDATE supermarket_sales SET Sales=0", tmp_db)
        assert not ok

    def test_multiple_statements_blocked(self, tmp_db):
        ok, err = validate_sql(
            "SELECT 1; DROP TABLE supermarket_sales", tmp_db
        )
        assert not ok

    def test_empty_sql_blocked(self, tmp_db):
        ok, err = validate_sql("", tmp_db)
        assert not ok


class TestSyntaxErrors:
    """
    查詢不存在的欄位 → 應回傳錯誤
    """
    def test_bad_column(self, tmp_db):
        ok, err = validate_sql(
            "SELECT nonexistent_column FROM supermarket_sales", tmp_db
        )
        assert not ok


class TestValidatorNode:
    def test_unsupported_query_bypasses_sql(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DB_PATH", tmp_db)
        from src.agent.nodes.sql_validator import sql_validator_node
        state = {
            "sql_query": "SELECT 1",
            "retry_count": 0,
            "intent": {"query_type": "unsupported", "is_prediction": True},
        }
        result = sql_validator_node(state)
        assert result["error"] == "unsupported_query"

    def test_retry_increments(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DB_PATH", tmp_db)
        from src.agent.nodes.sql_validator import sql_validator_node
        state = {
            "sql_query": "DROP TABLE supermarket_sales",
            "retry_count": 0,
            "intent": {},
        }
        result = sql_validator_node(state)
        assert result["retry_count"] == 1
        assert result["error"] == "validation_failed"

    def test_max_retries(self, tmp_db, monkeypatch):
        monkeypatch.setenv("DB_PATH", tmp_db)
        from src.agent.nodes.sql_validator import sql_validator_node
        state = {
            "sql_query": "DROP TABLE x",
            "retry_count": MAX_RETRIES - 1,
            "intent": {},
        }
        result = sql_validator_node(state)
        assert result["error"] == "max_retries_exceeded"
