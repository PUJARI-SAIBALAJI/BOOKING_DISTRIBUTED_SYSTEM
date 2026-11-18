import pytest

from backend.models.raft_applied_result import RaftAppliedResult


def valid_result():
    return {
        "nodeId": "node-1",
        "index": 1,
        "requestId": "request-001",
        "result": {
            "status": "success",
            "bookingId": "booking-001",
        },
    }


def test_valid_result():
    document = RaftAppliedResult.validate(valid_result())

    assert document["nodeId"] == "node-1"
    assert document["index"] == 1
    assert document["requestId"] == "request-001"


def test_result_is_preserved():
    document = RaftAppliedResult.validate(valid_result())

    assert document["result"]["status"] == "success"


def test_default_result_is_none():
    data = valid_result()
    del data["result"]

    document = RaftAppliedResult.validate(data)

    assert document["result"] is None


def test_missing_node_id():
    data = valid_result()
    del data["nodeId"]

    with pytest.raises(ValueError):
        RaftAppliedResult.validate(data)


def test_missing_index():
    data = valid_result()
    del data["index"]

    with pytest.raises(ValueError):
        RaftAppliedResult.validate(data)


def test_missing_request_id():
    data = valid_result()
    del data["requestId"]

    with pytest.raises(ValueError):
        RaftAppliedResult.validate(data)


def test_invalid_index():
    data = valid_result()
    data["index"] = "invalid"

    with pytest.raises(ValueError):
        RaftAppliedResult.validate(data)


def test_empty_request_id():
    data = valid_result()
    data["requestId"] = " "

    with pytest.raises(ValueError):
        RaftAppliedResult.validate(data)