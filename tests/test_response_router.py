"""
test_response_router.py — Unit tests for response_router.route_response()
"""
import sys, pathlib
sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))

import pytest
from src.agent.nodes.response_router import route_response


def _state(user_input="", results=None, intent=None, error=None):
    return {
        "user_input": user_input,
        "query_results": results or [],
        "intent": intent or {"visualization_hint": "verbal", "chart_type": None},
        "error": error,
    }


class TestVerbalRoute:
    """
    有錯誤、空結果、單一數值 → 應回傳 verbal
    """
    def test_error_returns_verbal(self):
        r = route_response(_state(results=[{"col": 1}], error="some_error"))
        assert r["response_format"] == "verbal"

    def test_empty_results_returns_verbal(self):
        r = route_response(_state(results=[]))
        assert r["response_format"] == "verbal"

    def test_single_value_returns_verbal(self):
        r = route_response(_state(results=[{"count": 1000}]))
        assert r["response_format"] == "verbal"


class TestTableRoute:
    """
    含「列出」關鍵字、intent 為 table → 應回傳 table
    """
    def test_list_keyword_returns_table(self):
        results = [{"Branch": "Alex", "Sales": 100, "Date": "2019-01-01"} for _ in range(5)]
        r = route_response(_state(user_input="列出所有分店銷售", results=results))
        assert r["response_format"] == "table"

    def test_detail_intent_returns_table(self):
        results = [{"id": i, "val": i * 10} for i in range(10)]
        r = route_response(_state(
            results=results,
            intent={"visualization_hint": "table", "chart_type": None},
        ))
        assert r["response_format"] == "table"


class TestChartRoute:
    """
    含比較／佔比／trend／pie 關鍵字 → 應回傳 chart，並對應正確的 chart_type（line / pie / bar）
    """
    def test_chart_keyword_zh_returns_chart(self):
        results = [{"product": f"P{i}", "sales": i * 100.0} for i in range(6)]
        r = route_response(_state(user_input="比較各產品銷售佔比", results=results))
        assert r["response_format"] == "chart"

    def test_chart_keyword_en_returns_chart(self):
        results = [{"product": f"P{i}", "sales": i * 100.0} for i in range(6)]
        r = route_response(_state(user_input="compare sales by product", results=results))
        assert r["response_format"] == "chart"

    def test_trend_keyword_uses_line_chart(self):
        results = [{"month": f"2019-0{i}", "sales": i * 100.0} for i in range(1, 4)]
        r = route_response(_state(user_input="月份趨勢", results=results))
        assert r["response_format"] == "chart"
        assert r["chart_type"] == "line"

    def test_pie_keyword_uses_pie_chart(self):
        results = [{"line": f"L{i}", "pct": i * 10.0} for i in range(1, 7)]
        r = route_response(_state(user_input="各產品線銷售佔比", results=results))
        assert r["chart_type"] == "pie"

    def test_intent_chart_hint_returns_chart(self):
        results = [{"branch": "A", "sales": 100.0}, {"branch": "B", "sales": 200.0}]
        r = route_response(_state(
            results=results,
            intent={"visualization_hint": "chart", "chart_type": "bar"},
        ))
        assert r["response_format"] == "chart"
        assert r["chart_type"] == "bar"
