import pytest

from backend.models.raft_log_entry import RaftLogEntry


def valid_entry():
    return {
        "nodeId": "node-1",
        "index": 1,
        "term": 1,
        "requestId": "request-001",
        "command": {
            "type": "BOOK_SEATS",
            "bookingId": "booking-001",
        },
    }


def test_valid_entry():
    entry = RaftLogEntry.validate(valid_entry())

    assert entry["nodeId"] == "node-1"
    assert entry["index"] == 1
    assert entry["term"] == 1


def test_command_is_preserved():
    entry = RaftLogEntry.validate(valid_entry())

    assert entry["command"]["type"] == "BOOK_SEATS"


def test_missing_node_id():
    data = valid_entry()
    del data["nodeId"]

    with pytest.raises(ValueError):
        RaftLogEntry.validate(data)


def test_missing_command():
    data = valid_entry()
    del data["command"]

    with pytest.raises(ValueError):
        RaftLogEntry.validate(data)


def test_negative_index():
    data = valid_entry()
    data["index"] = -1

    with pytest.raises(ValueError):
        RaftLogEntry.validate(data)


def test_negative_term():
    data = valid_entry()
    data["term"] = -1

    with pytest.raises(ValueError):
        RaftLogEntry.validate(data)


def test_empty_request_id():
    data = valid_entry()
    data["requestId"] = " "

    with pytest.raises(ValueError):
        RaftLogEntry.validate(data)


def test_empty_node_id():
    data = valid_entry()
    data["nodeId"] = " "

    with pytest.raises(ValueError):
        RaftLogEntry.validate(data)