import pytest

from backend.models.raft_state import RaftState


def valid_state():
    return {
        "_id": "node-1",
        "clusterId": "flashreserve-cluster",
    }


def test_default_values():
    state = RaftState.prepare(valid_state())

    assert state["currentTerm"] == 0
    assert state["votedFor"] is None
    assert state["commitIndex"] == 0
    assert state["lastApplied"] == 0
    assert state["clusterConfigVersion"] == 1


def test_cluster_configuration():
    data = valid_state()
    data["configuration"] = {"nodes": ["node-1", "node-2"]}

    state = RaftState.prepare(data)

    assert state["configuration"]["nodes"] == [
        "node-1", "node-2"
    ]


def test_custom_term():
    data = valid_state()
    data["currentTerm"] = 5

    state = RaftState.prepare(data)

    assert state["currentTerm"] == 5


def test_custom_commit_index():
    data = valid_state()
    data["commitIndex"] = 10

    state = RaftState.prepare(data)

    assert state["commitIndex"] == 10


def test_missing_id():
    with pytest.raises(KeyError):
        RaftState.prepare({})