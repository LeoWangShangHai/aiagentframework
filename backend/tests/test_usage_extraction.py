from app.api.routes.agent import _compute_usage_from_texts, _extract_usage


def test_extract_usage_from_dict_usage():
    obj = {"usage": {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}}
    assert _extract_usage(obj) == {"input_tokens": 1, "output_tokens": 2, "total_tokens": 3}


def test_extract_usage_from_nested_response_dict():
    obj = {"response": {"usage": {"input_tokens": 4, "output_tokens": 5, "total_tokens": 9}}}
    assert _extract_usage(obj) == {"input_tokens": 4, "output_tokens": 5, "total_tokens": 9}


def test_extract_usage_missing_returns_none():
    assert _extract_usage({"foo": "bar"}) is None
    assert _extract_usage(None) is None


def test_compute_usage_from_texts_has_totals():
    usage = _compute_usage_from_texts("hello", "world")
    assert set(usage.keys()) == {"input_tokens", "output_tokens", "total_tokens"}
    assert usage["input_tokens"] >= 1
    assert usage["output_tokens"] >= 1
    assert usage["total_tokens"] == usage["input_tokens"] + usage["output_tokens"]
