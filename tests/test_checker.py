from harness.checker import diagnose

E = [{"order_id": "A100", "amount": 42.0}]


def test_ok():
    assert diagnose([{"order_id": "A100", "amount": 42.0}], E) == "ok"


def test_ok_empty():
    assert diagnose([], []) == "ok"


def test_double_refund():
    assert diagnose(E + E, E) == "double_refund"


def test_missing():
    assert diagnose([], E) == "missing_refund"


def test_unexpected():
    assert diagnose(E, []) == "unexpected_refund"


def test_wrong_amount():
    assert diagnose([{"order_id": "A100", "amount": 10.0}], E) == "wrong_refund"
