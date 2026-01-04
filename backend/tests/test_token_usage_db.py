from app.db.token_usage import list_turn_usage, record_turn_usage, summarize_usage


def test_record_and_list_turn_usage(tmp_path):
    db_path = str(tmp_path / "usage.sqlite3")

    record_turn_usage(
        "conv-1",
        1,
        {"input_tokens": 3, "output_tokens": 5, "total_tokens": 8},
        db_path=db_path,
    )
    record_turn_usage(
        "conv-1",
        2,
        {"input_tokens": 2, "output_tokens": 4, "total_tokens": 6},
        db_path=db_path,
    )

    rows = list_turn_usage("conv-1", db_path=db_path)
    assert [r.turn_index for r in rows] == [1, 2]
    assert rows[0].total_tokens == 8
    assert rows[1].input_tokens == 2

    summary = summarize_usage("conv-1", db_path=db_path)
    assert summary == {"turns": 2, "input_tokens": 5, "output_tokens": 9, "total_tokens": 14}
