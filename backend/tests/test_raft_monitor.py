import time

from frontend.components.raft_monitor import _build_monitor_rows
from frontend.utils.operating_mode import RAFT_NODES


def test_monitor_builds_consistent_rows_when_ack_and_nodes_are_missing():
    statuses = [{
        "nodeId": "node-1",
        "role": "leader",
        "currentTerm": 12,
        "available": True,
        "healthy": True,
        "topologyMatches": True,
        "rpcConnected": True,
        "database": {"connected": True},
        "replicationAck": "ACKNOWLEDGED",
        "observed_at": time.time(),
    }]

    fresh_statuses, rows = _build_monitor_rows(statuses, time.time() * 1000)

    assert len(fresh_statuses) == len(RAFT_NODES) == len(rows)
    assert rows[0]["Replication ACK"] == "ACKNOWLEDGED"
    assert rows[0]["Term"] == "12"
    assert rows[1]["Node ID"] == "node-2"
    assert rows[1]["Replication ACK"] == "UNKNOWN"
    assert rows[1]["Term"] == "—"
    assert rows[1]["Status"] == "UNAVAILABLE"
    assert all(
        isinstance(row[column], str)
        for row in rows
        for column in ("Term", "Replication ACK")
    )


def test_monitor_accepts_status_without_replication_ack():
    statuses = [
        {
            "node_id": node_id,
            "currentTerm": 9,
            "available": False,
            "observed_at": time.time(),
        }
        for node_id, _ in RAFT_NODES
    ]

    _fresh_statuses, rows = _build_monitor_rows(statuses, time.time() * 1000)

    assert len(rows) == len(RAFT_NODES)
    assert all(row["Replication ACK"] == "UNKNOWN" for row in rows)
    assert all(row["Term"] == "9" for row in rows)
