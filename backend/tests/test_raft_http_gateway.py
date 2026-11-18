import json
import time
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.raft.http_gateway import RaftGatewayError, RaftHttpGateway


def _status(node_id, *, role="follower", term=4):
    return {
        "nodeId": node_id,
        "role": role,
        "leaderId": "node-1" if role == "leader" else None,
        "currentTerm": term,
        "available": True,
        "healthy": True,
        "topologyMatches": True,
        "lastQuorumAt": time.time() * 1000,
        "lastQuorumAcknowledgements": 4,
        "electionTimeoutMs": 1000,
    }


def test_gateway_requires_healthy_majority_before_returning_leader():
    gateway = object.__new__(RaftHttpGateway)
    leader = _status("node-1", role="leader")
    gateway.get_cluster_status = Mock(return_value={
        "majorityRequired": 4,
        "nodes": [
            leader,
            _status("node-2"),
            _status("node-3"),
            {
                **_status("node-4"),
                "healthy": False,
            },
            {
                **_status("node-5"),
                "available": False,
                "healthy": False,
            },
            {
                **_status("node-6"),
                "available": False,
                "healthy": False,
            },
            {
                **_status("node-7"),
                "available": False,
                "healthy": False,
            },
        ],
    })

    with pytest.raises(RaftGatewayError) as error:
        gateway.get_leader()

    assert error.value.code == "RAFT_NO_QUORUM"


def test_gateway_selects_current_leader_after_quorum_check():
    gateway = object.__new__(RaftHttpGateway)
    leader = _status("node-1", role="leader", term=5)
    gateway.get_cluster_status = Mock(return_value={
        "majorityRequired": 4,
        "nodes": [
            leader,
            _status("node-2", term=5),
            _status("node-3", term=5),
            _status("node-4", term=5),
        ],
    })

    assert gateway.get_leader() == leader


def test_gateway_reports_replication_ack_from_the_leader_for_each_follower():
    statuses = [
        _status("node-1", role="leader"),
        _status("node-2"),
        {
            **_status("node-3"),
            "available": False,
            "healthy": False,
        },
    ]
    statuses[0]["replicationProgress"] = {
        "node-2": {
            "ackStatus": "ACKNOWLEDGED",
            "nextIndex": 5,
            "matchIndex": 4,
        },
        "node-3": {
            "ackStatus": "UNREACHABLE",
            "nextIndex": 3,
            "matchIndex": 2,
            "lastError": "RpcError: unavailable",
        },
    }

    RaftHttpGateway._attach_replication_acknowledgements(
        statuses,
        [statuses[0]],
    )

    assert statuses[0]["replicationAck"] == "ACKNOWLEDGED"
    assert statuses[1]["replicationAck"] == "ACKNOWLEDGED"
    assert statuses[2]["replicationAck"] == "UNREACHABLE"
    assert statuses[2]["replicationAckDetails"]["lastError"] == "RpcError: unavailable"


def test_gateway_returns_committed_command_result():
    gateway = object.__new__(RaftHttpGateway)
    leader = _status("node-1", role="leader", term=5)
    gateway.get_leader = Mock(return_value=leader)
    gateway.rpc_timeout = 1
    gateway.stubs = {
        "node-1": SimpleNamespace(
            SubmitCommand=Mock(return_value=SimpleNamespace(
                committed=True,
                success=True,
                leader_id="node-1",
                result_payload=json.dumps({"success": True}).encode("utf-8"),
            ))
        )
    }

    result = gateway.submit_command(
        "request-1",
        "TEST",
        {"value": "ok"},
    )

    assert result == {
        "leaderId": "node-1",
        "term": 5,
        "commandId": "request-1",
        "result": {"success": True},
    }
    request = gateway.stubs["node-1"].SubmitCommand.call_args.args[0]
    assert request.command_id == "request-1"
    assert json.loads(request.command_payload) == {"value": "ok"}
