from app.services.aelin_utils import escape_sql_like, normalize_positive_ints


def test_normalize_positive_ints_filters_and_caps():
    out = normalize_positive_ints([3, "2", -1, "x", 3, 0], cap=3)
    assert out == [2, 3]


def test_normalize_positive_ints_cap_none_and_zero():
    assert normalize_positive_ints([1, 2, 3], cap=None) == [1, 2, 3]
    assert normalize_positive_ints([1, 2, 3], cap=0) == [1]


def test_escape_sql_like_escapes_wildcards():
    escaped = escape_sql_like(r"a%b_c\z")
    assert escaped == r"a\%b\_c\\z"
