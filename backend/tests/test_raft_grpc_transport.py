import grpc
import socket
import threading

import pytest

from concurrent import futures

from backend.grpc.proto import raft_pb2
from backend.grpc.proto import raft_pb2_grpc

from backend.raft.grpc_transport import (
    RaftGrpcServicer,
    RaftGrpcTransport,
    RaftPortBindError,
)
from backend.raft.raft_node import RaftNode


class FakeNode:

    FOLLOWER = "follower"
    CANDIDATE = "candidate"
    LEADER = "leader"

    def __init__(self):

        self.node_id = "node-1"
        self.members = ["node-1", "node-2", "node-3"]
        self.current_term = 1
        self.state = self.FOLLOWER
        self.leader_id = None

    def request_vote(self, **kwargs):

        return {
            "term": kwargs["term"],
            "vote_granted": True
        }

    def append_entries(self, **kwargs):

        return {
            "term": kwargs["term"],
            "success": True,
            "match_index": 0
        }

    def get_status(self):

        return {
            "state": self.state,
            "currentTerm": self.current_term,
            "commitIndex": 0,
            "lastApplied": 0,
            "lastLogIndex": 0
        }


class FakeTransport:
    def __init__(self):
        self.status_requests = []

    def get_peer_status(self, peer_id):
        self.status_requests.append(peer_id)
        raise RuntimeError("Peer unavailable")


def test_occupied_port_is_reported_without_starting_duplicate_server():
    node = FakeNode()
    transport = RaftGrpcTransport(node, {"node-1": "127.0.0.1:1"})
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        listener.listen()
        port = listener.getsockname()[1]
        try:
            with pytest.raises(RaftPortBindError, match=f"node-1.*port {port}"):
                transport.start_server(host="127.0.0.1", port=port)
        finally:
            transport.close()


def test_unreachable_vote_logs_real_grpc_status_and_peer(caplog):
    node = FakeNode()
    node.lock = threading.RLock()
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        address = f"127.0.0.1:{listener.getsockname()[1]}"
        transport = RaftGrpcTransport(node, {"node-2": address})
        try:
            with pytest.raises(grpc.RpcError) as failure:
                transport.request_vote("node-2", 3, "node-1", 0, 0)
        finally:
            transport.close()
    assert "peer=node-2" in caplog.text
    assert f"address={address}" in caplog.text
    assert "method=RequestVote" in caplog.text
    assert f"status={failure.value.code().name}" in caplog.text
    assert "request_term=3" in caplog.text
    assert "channel=" in caplog.text


def test_request_vote_over_grpc():

    node = FakeNode()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=2)
    )

    raft_pb2_grpc.add_RaftServiceServicer_to_server(
        RaftGrpcServicer(node, FakeTransport()),
        server
    )

    port = server.add_insecure_port("127.0.0.1:0")

    server.start()

    channel = grpc.insecure_channel(
        f"127.0.0.1:{port}"
    )

    try:

        stub = raft_pb2_grpc.RaftServiceStub(channel)

        response = stub.RequestVote(
            raft_pb2.RequestVoteRequest(
                term=2,
                candidate_id="node-2",
                last_log_index=0,
                last_log_term=0
            ),
            timeout=2
        )

        assert response.vote_granted is True
        assert response.voter_id == "node-1"

    finally:

        channel.close()
        server.stop(grace=0)


def test_append_entries_over_grpc():

    node = FakeNode()

    server = grpc.server(
        futures.ThreadPoolExecutor(max_workers=2)
    )

    raft_pb2_grpc.add_RaftServiceServicer_to_server(
        RaftGrpcServicer(node, FakeTransport()),
        server
    )

    port = server.add_insecure_port("127.0.0.1:0")

    server.start()

    channel = grpc.insecure_channel(
        f"127.0.0.1:{port}"
    )

    try:

        stub = raft_pb2_grpc.RaftServiceStub(channel)

        response = stub.AppendEntries(
            raft_pb2.AppendEntriesRequest(
                term=2,
                leader_id="node-2",
                prev_log_index=0,
                prev_log_term=0,
                leader_commit=0
            ),
            timeout=2
        )

        assert response.success is True
        assert response.follower_id == "node-1"

    finally:

        channel.close()
        server.stop(grace=0)


def test_unsupported_snapshot_still_persists_a_higher_term():
    class MemoryStore:
        def __init__(self):
            self.data = {}

        def load(self, node_id):
            return self.data.get(node_id)

        def save(self, node_id, state):
            self.data[node_id] = {
                **state,
                "log": list(state["log"]),
                "appliedResults": list(state["appliedResults"]),
            }

    members = [f"node-{index}" for index in range(1, 8)]
    store = MemoryStore()
    node = RaftNode("node-1", members, store)
    servicer = RaftGrpcServicer(node, FakeTransport())

    response = servicer.InstallSnapshot(
        raft_pb2.InstallSnapshotRequest(
            term=5,
            leader_id="node-2",
        ),
        None,
    )
    stale_response = servicer.InstallSnapshot(
        raft_pb2.InstallSnapshotRequest(
            term=4,
            leader_id="node-3",
        ),
        None,
    )

    assert response.success is False
    assert response.term == 5
    assert stale_response.term == 5
    assert node.current_term == 5
    assert node.voted_for is None
    assert node.leader_id == "node-2"
    assert store.data["node-1"]["currentTerm"] == 5


def test_cluster_status_reports_local_node_without_recursive_peer_queries():
    node = FakeNode()
    transport = FakeTransport()
    servicer = RaftGrpcServicer(node, transport)

    response = servicer.GetClusterStatus(
        raft_pb2.GetClusterStatusRequest(requester_id="node-2"),
        None,
    )

    assert response.has_leader is False
    assert response.nodes == [
        raft_pb2.NodeStatus(
            node_id="node-1",
            state="follower",
            current_term=1,
            commit_index=0,
            last_applied=0,
            last_log_index=0,
            reachable=True,
            configuration_json="{}",
            replication_progress_json="{}",
        )
    ]
    assert transport.status_requests == []


def test_cluster_status_uses_cached_mongodb_topology_without_blocking_ping():
    class Topology:
        def has_writable_server(self):
            return False

    class Database:
        name = "raft-node"
        client = type(
            "Client",
            (),
            {
                "topology_description": Topology(),
                "admin": type(
                    "Admin",
                    (),
                    {
                        "command": staticmethod(
                            lambda *_args, **_kwargs: (_ for _ in ()).throw(
                                AssertionError("status must not perform a blocking ping")
                            )
                        )
                    },
                )(),
            },
        )()

    node = FakeNode()
    node.store = type("Store", (), {"database": Database()})()
    servicer = RaftGrpcServicer(node, FakeTransport())

    response = servicer.GetClusterStatus(
        raft_pb2.GetClusterStatusRequest(requester_id="node-2"),
        None,
    )

    assert response.nodes[0].database_connected is False
    assert response.nodes[0].database_name == "raft-node"