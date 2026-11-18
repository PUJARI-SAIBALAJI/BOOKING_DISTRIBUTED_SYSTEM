import json
import threading

import grpc
import pytest
from pymongo.errors import ServerSelectionTimeoutError

from backend.raft.raft_node import RaftNode


class FakeStore:

    def __init__(self):
        self.data = {}

    def load(self, node_id):
        return self.data.get(node_id)

    def save(self, node_id, state):

        self.data[node_id] = {
            **state,
            "log": [entry.copy() for entry in state["log"]],
            "appliedResults": [
                item.copy()
                for item in state["appliedResults"]
            ]
        }


def create_node(node_id="node-1"):

    members = [
        "node-1",
        "node-2",
        "node-3",
        "node-4",
        "node-5",
        "node-6",
        "node-7"
    ]

    store = FakeStore()

    node = RaftNode(
        node_id=node_id,
        members=members,
        store=store
    )

    return node, store


def test_initial_node_state():

    node, _ = create_node()

    assert node.state == RaftNode.FOLLOWER

    assert node.current_term == 0

    assert node.voted_for is None


def test_node_has_seven_members():

    node, _ = create_node()

    assert len(node.members) == 7


def test_election_timeouts_are_distinct_and_change_preference_by_term():
    members = [f"node-{index}" for index in range(1, 8)]
    nodes = [
        RaftNode(
            node_id=node_id,
            members=members,
            store=FakeStore(),
            cluster_id="randomized-election-test",
            election_timeout_min=2,
            election_timeout_max=4,
        )
        for node_id in members
    ]

    earliest_nodes = set()
    for term in range(20):
        timeouts = {}
        for node in nodes:
            node.current_term = term
            node.election_timeout = node._random_timeout()
            timeouts[node.node_id] = node.election_timeout

        assert len(set(timeouts.values())) == len(members)
        earliest_nodes.add(min(timeouts, key=timeouts.get))

    assert len(earliest_nodes) > 1


def test_all_configured_nodes_can_become_leader():
    members = [f"node-{index}" for index in range(1, 8)]
    for node_id in members:
        node = RaftNode(node_id, members, FakeStore())
        node.start()
        try:
            assert node.start_election(
                lambda _peer, term, *_args: {
                    "term": term,
                    "vote_granted": True,
                }
            )
            assert node.state == RaftNode.LEADER
        finally:
            node.stop()


def test_failed_election_persistence_does_not_advance_the_term_or_request_votes():
    node, store = create_node()
    node.start()
    original_save = store.save
    requested_peers = []

    def fail_save(node_id, state):
        if state["currentTerm"] == 1:
            raise ServerSelectionTimeoutError("MongoDB unavailable")
        original_save(node_id, state)

    store.save = fail_save
    try:
        with pytest.raises(ServerSelectionTimeoutError, match="MongoDB unavailable"):
            node.start_election(
                lambda peer, *_args: requested_peers.append(peer)
            )
    finally:
        node.stop()

    assert node.current_term == 0
    assert node.state == RaftNode.FOLLOWER
    assert node.voted_for is None
    assert requested_peers == []


def test_submitted_command_has_replicated_timestamp():
    node, _ = create_node()
    node.state = RaftNode.LEADER
    node.current_term = 1

    result = node.submit_command(
        "request-1",
        "TEST",
        {"value": 1},
    )

    entry = node.log[0]
    payload = json.loads(entry["command"]["payload"])

    assert result["success"] is True
    assert entry["timestamp"] == payload["_raftTimestamp"]
    assert payload["requestId"] == "request-1"
    assert payload["operationType"] == "TEST"
    assert payload["operationId"]


def test_duplicate_request_id_with_same_payload_reuses_log_entry():
    node, _ = create_node()
    node.state = RaftNode.LEADER
    node.current_term = 1

    first = node.submit_command("request-1", "TEST", {"value": 1})
    replay = node.submit_command("request-1", "TEST", {"value": 1})

    assert first["index"] == replay["index"] == 1
    assert len(node.log) == 1


def test_duplicate_request_id_with_different_payload_is_rejected():
    node, _ = create_node()
    node.state = RaftNode.LEADER
    node.current_term = 1
    node.submit_command("request-1", "TEST", {"value": 1})

    try:
        node.submit_command("request-1", "TEST", {"value": 2})
    except ValueError as error:
        assert "reused" in str(error)
    else:
        raise AssertionError("Mismatched command reuse must fail")


def test_append_entries_rejects_noncontiguous_indexes():
    node, _ = create_node()
    response = node.append_entries(
        term=1,
        leader_id="node-2",
        prev_log_index=0,
        prev_log_term=0,
        entries=[{
            "index": 2,
            "term": 1,
            "requestId": "request-2",
            "command": {"type": "TEST", "payload": "{}"},
        }],
        leader_commit=0,
    )

    assert response["success"] is False
    assert node.log == []


def test_append_entries_recovers_a_follower_and_persists_before_ack():
    node, store = create_node()
    node.log = [{
        "index": 1,
        "term": 1,
        "requestId": "request-1",
        "command": {"type": "TEST", "payload": '{"value":1}'},
    }]
    node.commit_index = 1
    node._persist()
    recovered_entry = {
        "index": 2,
        "term": 3,
        "requestId": "request-2",
        "command": {"type": "TEST", "payload": '{"value":2}'},
    }

    response = node.append_entries(
        term=3,
        leader_id="node-2",
        prev_log_index=1,
        prev_log_term=1,
        entries=[recovered_entry],
        leader_commit=2,
    )

    assert response["success"] is True
    assert response["match_index"] == 2
    assert node.log[-1] == recovered_entry
    assert node.commit_index == 2
    assert store.data[node.node_id]["log"][-1] == recovered_entry
    assert store.data[node.node_id]["commitIndex"] == 2


def test_append_entries_rejects_same_term_conflict_without_partial_mutation():
    node, store = create_node()
    node.log = [
        {
            "index": 1,
            "term": 1,
            "requestId": "request-1",
            "command": {"type": "TEST", "payload": '{"value":1}'},
        },
        {
            "index": 2,
            "term": 2,
            "requestId": "request-2",
            "command": {"type": "TEST", "payload": '{"value":2}'},
        },
    ]
    node._persist()
    original_log = [entry.copy() for entry in node.log]

    response = node.append_entries(
        term=2,
        leader_id="node-3",
        prev_log_index=0,
        prev_log_term=0,
        entries=[
            {
                "index": 1,
                "term": 1,
                "requestId": "request-1",
                "command": {"type": "TEST", "payload": '{"value":1}'},
            },
            {
                "index": 2,
                "term": 2,
                "requestId": "conflict",
                "command": {"type": "TEST", "payload": '{"value":3}'},
            },
        ],
        leader_commit=0,
    )

    assert response["success"] is False
    assert node.log == original_log
    assert store.data[node.node_id]["log"] == original_log


def test_append_entries_replaces_conflicting_uncommitted_suffix():
    node, store = create_node()
    node.log = [
        {
            "index": 1,
            "term": 1,
            "requestId": "committed",
            "command": {"type": "TEST", "payload": '{"value":1}'},
        },
        {
            "index": 2,
            "term": 2,
            "requestId": "old-2",
            "command": {"type": "TEST", "payload": '{"value":2}'},
        },
        {
            "index": 3,
            "term": 2,
            "requestId": "old-3",
            "command": {"type": "TEST", "payload": '{"value":3}'},
        },
    ]
    node.commit_index = 1
    node._persist()

    replacement_entries = [
        {
            "index": 2,
            "term": 3,
            "requestId": "new-2",
            "command": {"type": "TEST", "payload": '{"value":20}'},
        },
        {
            "index": 3,
            "term": 3,
            "requestId": "new-3",
            "command": {"type": "TEST", "payload": '{"value":30}'},
        },
    ]
    response = node.append_entries(
        term=3,
        leader_id="node-2",
        prev_log_index=1,
        prev_log_term=1,
        entries=replacement_entries,
        leader_commit=3,
    )

    assert response["success"] is True
    assert response["match_index"] == 3
    assert node.log[1:] == replacement_entries
    assert store.data[node.node_id]["log"][1:] == replacement_entries
    assert node.commit_index == 3


def test_append_entries_rejects_entry_from_a_future_term():
    node, _ = create_node()
    response = node.append_entries(
        term=1,
        leader_id="node-2",
        prev_log_index=0,
        prev_log_term=0,
        entries=[{
            "index": 1,
            "term": 2,
            "requestId": "request-1",
            "command": {"type": "TEST", "payload": "{}"},
        }],
        leader_commit=0,
    )

    assert response["success"] is False
    assert node.log == []


def test_heartbeat_does_not_commit_unmatched_follower_suffix():
    node, store = create_node()
    node.log = [
        {"index": 1, "term": 1, "requestId": "a", "command": {"type": "TEST", "payload": "{}"}},
        {"index": 2, "term": 2, "requestId": "b", "command": {"type": "TEST", "payload": "{}"}},
    ]
    response = node.append_entries(3, "node-2", 1, 1, [], 2)

    assert response["success"]
    assert node.commit_index == 1
    assert store.data[node.node_id]["commitIndex"] == 1


def test_rejected_malformed_append_persists_higher_term():
    node, store = create_node()
    node.request_vote(1, "node-3", 0, 0)
    response = node.append_entries(2, "node-2", 0, 0, [{
        "index": 2, "term": 2, "requestId": "bad",
        "command": {"type": "TEST", "payload": "{}"},
    }], 0)

    assert not response["success"]
    assert store.data[node.node_id]["currentTerm"] == 2
    assert store.data[node.node_id]["votedFor"] is None


def test_heartbeat_never_moves_commit_index_backwards():
    node, _ = create_node()
    node.log = [
        {"index": i, "term": 1, "requestId": str(i), "command": {"type": "TEST", "payload": "{}"}}
        for i in range(1, 4)
    ]
    node.commit_index = 2
    response = node.append_entries(2, "node-2", 1, 1, [], 3)
    assert response["success"]
    assert node.commit_index == 2


def test_stale_replication_response_cannot_update_new_leader_progress():
    node, _ = create_node()
    node.state = RaftNode.LEADER
    node.current_term = 1
    node.next_index["node-2"] = 1
    node.match_index["node-2"] = 0

    def stale_response(*_args):
        node.current_term = 2
        node.state = RaftNode.LEADER
        return {"term": 1, "success": True, "match_index": 0}

    assert not node.replicate_to_peer("node-2", stale_response)
    assert node.match_index["node-2"] == 0


def test_successful_replication_ack_does_not_regress_progress():
    node, _ = create_node()
    node.state = RaftNode.LEADER
    node.current_term = 1
    node.log = [
        {
            "index": index,
            "term": 1,
            "requestId": f"request-{index}",
            "command": {"type": "TEST", "payload": "{}"},
        }
        for index in range(1, 4)
    ]
    node.next_index["node-2"] = 1
    node.match_index["node-2"] = 3

    assert node.replicate_to_peer(
        "node-2",
        lambda *_args: {"term": 1, "success": True, "match_index": 1},
    )

    assert node.match_index["node-2"] == 3
    assert node.next_index["node-2"] == 4
    assert node.get_status()["replicationProgress"]["node-2"]["ackStatus"] == "ACKNOWLEDGED"


def test_failed_replication_records_unreachable_status_and_rpc_error():
    node, _ = create_node()
    node.state = RaftNode.LEADER
    node.current_term = 1
    node.next_index["node-2"] = 1

    class UnavailableError(grpc.RpcError):
        def code(self):
            return grpc.StatusCode.UNAVAILABLE

        def __str__(self):
            return "peer connection refused"

    def fail(*_args):
        raise UnavailableError()

    assert not node.replicate_to_peer("node-2", fail)
    progress = node.get_status()["replicationProgress"]["node-2"]
    assert progress["ackStatus"] == "UNREACHABLE"
    assert "connection refused" in progress["lastError"]


def test_log_conflict_is_reported_as_catching_up():
    node, _ = create_node()
    node.state = RaftNode.LEADER
    node.current_term = 1
    node.log = [{
        "index": 1,
        "term": 1,
        "requestId": "request-1",
        "command": {"type": "TEST", "payload": "{}"},
    }]
    node.next_index["node-2"] = 2
    node.match_index["node-2"] = 0

    assert not node.replicate_to_peer(
        "node-2",
        lambda *_args: {
            "term": 1,
            "success": False,
            "match_index": 0,
            "conflict_index": 1,
            "conflict_term": 0,
        },
    )
    progress = node.get_status()["replicationProgress"]["node-2"]
    assert progress["ackStatus"] == "CATCHING UP"
    assert node.next_index["node-2"] == 1


def test_append_response_with_invalid_shape_is_failed_not_acknowledged():
    node, _ = create_node()
    node.state = RaftNode.LEADER
    node.current_term = 1
    node.next_index["node-2"] = 1

    assert not node.replicate_to_peer("node-2", lambda *_args: {"success": True})
    progress = node.get_status()["replicationProgress"]["node-2"]
    assert progress["ackStatus"] == "FAILED"
    assert progress["lastError"] == "Invalid AppendEntries response"


def test_non_quorum_cannot_commit_but_four_nodes_can():
    node, store = create_node()
    node.state = RaftNode.LEADER
    node.current_term = 1
    node.log = [{
        "index": 1,
        "term": 1,
        "requestId": "request-1",
        "command": {"type": "TEST", "payload": "{}"},
    }]
    node.match_index[node.node_id] = 1
    for peer_id in ("node-2", "node-3"):
        node.match_index[peer_id] = 1

    node._advance_commit_index()
    assert node.commit_index == 0
    assert store.data[node.node_id]["commitIndex"] == 0

    node.match_index["node-4"] = 1
    node._advance_commit_index()
    assert node.commit_index == 1
    assert store.data[node.node_id]["commitIndex"] == 1


def test_failed_leader_log_persistence_does_not_send_entry_for_replication():
    class FailingStore(FakeStore):
        fail = False

        def save(self, node_id, state):
            if self.fail:
                raise OSError("disk unavailable")
            super().save(node_id, state)

    members = [f"node-{index}" for index in range(1, 8)]
    store = FailingStore()
    node = RaftNode("node-1", members, store)
    node.state = RaftNode.LEADER
    node.current_term = 1
    store.fail = True

    try:
        node.submit_command("request-1", "TEST", {"value": 1})
    except OSError as error:
        assert str(error) == "disk unavailable"
    else:
        raise AssertionError("A non-durable leader entry must not be submitted")

    assert node.log == []
    assert node.match_index["node-1"] == 0


def test_follower_does_not_acknowledge_entries_when_persistence_fails():
    class FailingStore(FakeStore):
        fail = False

        def save(self, node_id, state):
            if self.fail:
                raise OSError("disk unavailable")
            super().save(node_id, state)

    members = [f"node-{index}" for index in range(1, 8)]
    store = FailingStore()
    node = RaftNode("node-1", members, store)
    node.current_term = 1
    node._persist()
    store.fail = True
    try:
        node.append_entries(
            term=1,
            leader_id="node-2",
            prev_log_index=0,
            prev_log_term=0,
            entries=[{
                "index": 1,
                "term": 1,
                "requestId": "request-1",
                "command": {"type": "TEST", "payload": "{}"},
            }],
            leader_commit=1,
        )
    except OSError as error:
        assert str(error) == "disk unavailable"
    else:
        raise AssertionError("A follower must not ACK a non-durable log entry")

    assert node.log == []
    assert node.commit_index == 0


def test_commit_index_rolls_back_when_commit_persistence_fails():
    class FailingStore(FakeStore):
        fail = False

        def save(self, node_id, state):
            if self.fail:
                raise OSError("disk unavailable")
            super().save(node_id, state)

    members = [f"node-{index}" for index in range(1, 8)]
    store = FailingStore()
    node = RaftNode("node-1", members, store)
    node.state = RaftNode.LEADER
    node.current_term = 1
    node.log = [{
        "index": 1,
        "term": 1,
        "requestId": "request-1",
        "command": {"type": "TEST", "payload": "{}"},
    }]
    node.match_index[node.node_id] = 1
    for peer_id in ("node-2", "node-3", "node-4"):
        node.match_index[peer_id] = 1
    node._persist()
    store.fail = True

    try:
        node._advance_commit_index()
    except OSError as error:
        assert str(error) == "disk unavailable"
    else:
        raise AssertionError("Commit must not advance without durable metadata")

    assert node.commit_index == 0


def test_majority_requires_four_votes():

    node, _ = create_node()

    node.votes_received = {
        "node-1",
        "node-2",
        "node-3"
    }

    assert node._has_majority() is False

    node.votes_received.add("node-4")

    assert node._has_majority() is True


def test_timed_election_rechecks_timeout_after_heartbeat():
    node, store = create_node()
    node.start()
    node.last_heartbeat -= node.election_timeout + 1
    assert node.check_election_timeout()

    node.append_entries(1, "node-2", 0, 0, [], 0)
    assert not node.start_election(lambda *_: None, require_timeout=True)
    assert node.current_term == 1
    assert store.data[node.node_id]["currentTerm"] == 1
    assert node.state == RaftNode.FOLLOWER


def test_election_does_not_count_stale_term_votes():
    node, _ = create_node()
    node.start()

    assert not node.start_election(
        lambda *_: {"term": 0, "vote_granted": True}
    )
    assert node.votes_received == {"node-1"}
    assert node.state == RaftNode.CANDIDATE


def test_election_reaches_majority_without_waiting_for_unavailable_peer():
    node, _ = create_node()
    node.start()
    blocked = threading.Event()

    def vote(peer_id, term, *_args):
        if peer_id == "node-2":
            blocked.wait(2)
            return {"term": term, "vote_granted": False}
        return {"term": term, "vote_granted": True}

    try:
        completed = threading.Event()
        result = []
        worker = threading.Thread(
            target=lambda: (result.append(node.start_election(vote)), completed.set())
        )
        worker.start()
        assert completed.wait(1), "unavailable peer blocked the election"
        assert result == [True]
        assert node.state == RaftNode.LEADER
    finally:
        blocked.set()
        worker.join(timeout=3)
        node.stop()


def test_late_higher_term_vote_response_steps_down_elected_leader():
    node, store = create_node()
    node.start()
    release = threading.Event()
    processed = threading.Event()

    def vote(peer_id, term, *_args):
        if peer_id == "node-2":
            release.wait(2)
            processed.set()
            return {"term": term + 1, "vote_granted": False}
        return {"term": term, "vote_granted": True}

    try:
        assert node.start_election(vote)
        assert node.state == RaftNode.LEADER
        release.set()
        assert processed.wait(1)
        for _ in range(100):
            with node.lock:
                if node.current_term == 2:
                    break
            threading.Event().wait(0.01)
        assert node.current_term == 2
        assert node.state == RaftNode.FOLLOWER
        assert store.data[node.node_id]["currentTerm"] == 2
    finally:
        release.set()
        node.stop()


def test_vote_granted_to_up_to_date_candidate():

    node, _ = create_node()

    response = node.request_vote(
        term=1,
        candidate_id="node-2",
        last_log_index=0,
        last_log_term=0
    )

    assert response["vote_granted"] is True

    assert node.voted_for == "node-2"


def test_node_rejects_second_vote_in_same_term():

    node, _ = create_node()

    node.request_vote(
        1,
        "node-2",
        0,
        0
    )

    response = node.request_vote(
        1,
        "node-3",
        0,
        0
    )

    assert response["vote_granted"] is False


def test_higher_term_updates_current_term():

    node, _ = create_node()

    node.request_vote(
        5,
        "node-2",
        0,
        0
    )

    assert node.current_term == 5


def test_rejects_outdated_candidate_log():

    node, _ = create_node()

    node.log = [
        {
            "index": 1,
            "term": 2,
            "requestId": "req-1",
            "command": {"type": "test"}
        }
    ]

    response = node.request_vote(
        3,
        "node-2",
        0,
        0
    )

    assert response["vote_granted"] is False


def test_append_entries_accepts_heartbeat():

    node, _ = create_node()

    response = node.append_entries(
        term=1,
        leader_id="node-2",
        prev_log_index=0,
        prev_log_term=0,
        entries=[],
        leader_commit=0
    )

    assert response["success"] is True

    assert node.leader_id == "node-2"


def test_append_entries_rejects_old_term():

    node, _ = create_node()

    node.current_term = 5

    response = node.append_entries(
        term=4,
        leader_id="node-2",
        prev_log_index=0,
        prev_log_term=0,
        entries=[],
        leader_commit=0
    )

    assert response["success"] is False


def test_log_replication():

    node, _ = create_node()

    entry = {
        "index": 1,
        "term": 1,
        "requestId": "req-1",
        "command": {
            "type": "booking.create"
        }
    }

    response = node.append_entries(
        term=1,
        leader_id="node-2",
        prev_log_index=0,
        prev_log_term=0,
        entries=[entry],
        leader_commit=0
    )

    assert response["success"] is True

    assert len(node.log) == 1


def test_node_status():

    node, _ = create_node()

    status = node.get_status()

    assert status["nodeId"] == "node-1"

    assert status["state"] == "follower"

    assert status["running"] is False


def test_persistent_term():

    node, store = create_node()

    node.request_vote(
        3,
        "node-2",
        0,
        0
    )

    restarted_node = RaftNode(
        node_id="node-1",
        members=node.members,
        store=store
    )

    assert restarted_node.current_term == 3

    assert restarted_node.voted_for == "node-2"