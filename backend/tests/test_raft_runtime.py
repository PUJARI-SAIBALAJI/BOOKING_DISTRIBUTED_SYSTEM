from backend.raft.raft_runtime import RaftRuntime
import threading
import time
from types import SimpleNamespace

class FakeNode:

    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"

    def __init__(self):

        self.node_id = "node-1"

        self.members = [
            "node-1",
            "node-2",
            "node-3",
            "node-4",
            "node-5",
            "node-6",
            "node-7"
        ]

        self.state = self.FOLLOWER
        self.current_term = 1
        self.running = False
        self.commit_index = 1
        self.last_applied = 0
        self.log = [{
            "index": 1,
            "term": 1,
            "requestId": "request-1",
            "command": {
                "type": "TEST",
                "payload": "{}",
            },
        }]
        self.applied_results = []

        # Match the actual RaftNode interface.
        self.lock = threading.RLock()

        self.replicated_peers = []

    def start(self):
        self.running = True

    def stop(self):
        self.running = False

    def check_election_timeout(self):
        return False

    def get_status(self):
        return {
            "state": self.state
        }

    def _persist(self):
        return None

    def record_replication_round(self, term, acknowledged_peers):
        self.replication_round = (term, acknowledged_peers)

    def replicate_to_peer(self, peer_id, callback):

        self.replicated_peers.append(peer_id)

        return True

class FakeTransport:

    def request_vote(self, *args):
        return {
            "term": 1,
            "vote_granted": True
        }

    def append_entries(self, *args):
        return {
            "term": 1,
            "success": True,
            "match_index": 0
        }


def test_runtime_initialization():

    node = FakeNode()

    runtime = RaftRuntime(
        node,
        FakeTransport()
    )

    assert runtime.running is False

    runtime.executor.shutdown(wait=True)


def test_runtime_starts_and_stops():

    node = FakeNode()

    runtime = RaftRuntime(
        node,
        FakeTransport()
    )

    runtime.start()

    assert runtime.running is True
    assert node.running is True

    runtime.stop()

    assert runtime.running is False
    assert node.running is False


def test_replication_targets_six_followers():

    node = FakeNode()

    runtime = RaftRuntime(
        node,
        FakeTransport()
    )

    node.state = node.LEADER

    runtime._replicate_to_followers()

    assert len(node.replicated_peers) == 6

    assert "node-1" not in node.replicated_peers

    assert set(node.replicated_peers) == {
        "node-2",
        "node-3",
        "node-4",
        "node-5",
        "node-6",
        "node-7"
    }

    runtime.executor.shutdown(wait=True)

def test_follower_does_not_replicate():

    node = FakeNode()

    runtime = RaftRuntime(
        node,
        FakeTransport()
    )

    node.state = node.FOLLOWER

    runtime._replicate_to_followers()

    assert len(node.replicated_peers) == 0

    runtime.executor.shutdown(wait=True)


def test_cluster_summary_separates_local_leader_and_peer_observation(caplog):
    node = FakeNode()
    node.last_leader_contact = time.monotonic()
    node.election_timeout = 4
    node.get_status = lambda: {
        "nodeId": "node-1", "state": "follower", "currentTerm": 5,
        "leaderId": "node-2", "lastQuorumAt": None, "lastLogIndex": 10,
        "commitIndex": 9, "lastApplied": 9, "replicationProgress": {},
    }

    class ObservedTransport:
        def get_peer_status(self, peer):
            return SimpleNamespace(
                state="leader" if peer == "node-2" else "follower",
                current_term=5, last_log_index=10, commit_index=9,
                last_applied=9, database_connected=True,
            )

    runtime = RaftRuntime(node, ObservedTransport())
    try:
        with caplog.at_level("INFO"):
            runtime._report_status()
        assert "known_leader=node-2" in caplog.text
        assert "node-2 leader AVAILABLE 5 10 9 9 CONNECTED" in caplog.text
        assert "leader local replication progress" not in caplog.text
    finally:
        runtime.executor.shutdown(wait=True)
        runtime.status_executor.shutdown(wait=True)


def test_follower_applies_committed_command():
    class StateMachine:
        def apply_command(self, **kwargs):
            return {"success": True, "result": {"applied": True}}

    node = FakeNode()
    runtime = RaftRuntime(node, FakeTransport(), StateMachine())

    runtime._apply_committed_entries()

    assert node.last_applied == 1
    assert node.applied_results == [{
        "index": 1,
        "requestId": "request-1",
        "result": {"success": True, "result": {"applied": True}},
    }]
    runtime.executor.shutdown(wait=True)