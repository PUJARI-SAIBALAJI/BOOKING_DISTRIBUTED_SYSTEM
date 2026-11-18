import json
import socket
import time

import grpc

from backend.grpc.proto import raft_pb2, raft_pb2_grpc
from backend.raft.grpc_transport import RaftGrpcTransport
from backend.raft.raft_node import RaftNode
from backend.raft.raft_runtime import RaftRuntime


class MemoryStore:
    def __init__(self):
        self.state = {}

    def load(self, node_id):
        return self.state.get(node_id)

    def save(self, node_id, state):
        self.state[node_id] = json.loads(json.dumps(state))


class RecordingStateMachine:
    def __init__(self):
        self.commands = []

    def apply_command(self, command_id, command_type, payload):
        result = {
            "success": True,
            "commandId": command_id,
            "commandType": command_type,
            "payload": json.loads(payload),
        }
        self.commands.append(result)
        return result


def _free_port():
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return listener.getsockname()[1]


def _wait_until(predicate, timeout=5):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return False


def _submit_command(address, command_id, booking_id):
    channel = grpc.insecure_channel(address)
    try:
        return raft_pb2_grpc.RaftServiceStub(channel).SubmitCommand(
            raft_pb2.SubmitCommandRequest(
                command_id=command_id,
                command_type="TEST_BOOKING",
                command_payload=json.dumps(
                    {"bookingId": booking_id}
                ).encode("utf-8"),
            ),
            timeout=10,
        )
    finally:
        channel.close()


def _stop_member(node_id, runtimes, transports):
    runtimes[node_id].stop()
    server = transports[node_id].server
    transports[node_id].close()
    server.stop(grace=0).wait(timeout=2)
    transports[node_id] = None


def test_seven_node_grpc_cluster_commits_applies_and_elects_after_leader_loss():
    members = [f"node-{index}" for index in range(1, 8)]
    addresses = {
        node_id: f"127.0.0.1:{_free_port()}"
        for node_id in members
    }
    nodes = {}
    stores = {}
    transports = {}
    runtimes = {}
    state_machines = {}

    try:
        for node_id in members:
            store = MemoryStore()
            node = RaftNode(
                node_id=node_id,
                members=members,
                store=store,
                cluster_id="isolated-test-cluster",
                topology_id="isolated-test-topology",
                election_timeout_min=20,
                election_timeout_max=30,
            )
            transport = RaftGrpcTransport(node, addresses)
            transport.start_server(
                host="127.0.0.1",
                port=int(addresses[node_id].rsplit(":", 1)[1]),
            )
            state_machine = RecordingStateMachine()
            runtime = RaftRuntime(node, transport, state_machine)
            nodes[node_id] = node
            transports[node_id] = transport
            state_machines[node_id] = state_machine
            runtimes[node_id] = runtime
            stores[node_id] = store

        for runtime in runtimes.values():
            runtime.start()

        leader = nodes["node-1"]
        assert leader.start_election(transports["node-1"].request_vote)
        assert _wait_until(
            lambda: leader.last_quorum_acknowledgements >= 4
        )

        response = _submit_command(
            addresses["node-1"],
            "isolated-booking-1",
            "booking-1",
        )
        assert response.success is True
        assert response.committed is True
        assert _wait_until(
            lambda: all(node.commit_index == 1 for node in nodes.values())
        )
        assert _wait_until(
            lambda: all(node.last_applied == 1 for node in nodes.values())
        )
        assert all(
            machine.commands[0]["commandId"] == "isolated-booking-1"
            for machine in state_machines.values()
        )

        follower_id = "node-3"
        _stop_member(follower_id, runtimes, transports)

        assert _wait_until(
            lambda: nodes["node-1"].get_status()["replicationProgress"][
                follower_id
            ]["ackStatus"] == "UNREACHABLE"
        )

        for index in (2, 3):
            response = _submit_command(
                addresses["node-1"],
                f"isolated-booking-{index}",
                f"booking-{index}",
            )
            assert response.success is True
            assert response.committed is True

        assert _wait_until(
            lambda: all(
                node.commit_index == 3
                for node_id, node in nodes.items()
                if node_id != follower_id
            )
        )

        restarted_node = RaftNode(
            node_id=follower_id,
            members=members,
            store=stores[follower_id],
            cluster_id="isolated-test-cluster",
            topology_id="isolated-test-topology",
            election_timeout_min=20,
            election_timeout_max=30,
        )
        restarted_transport = RaftGrpcTransport(restarted_node, addresses)
        restarted_transport.start_server(
            host="127.0.0.1",
            port=int(addresses[follower_id].rsplit(":", 1)[1]),
        )
        restarted_state_machine = RecordingStateMachine()
        restarted_runtime = RaftRuntime(
            restarted_node,
            restarted_transport,
            restarted_state_machine,
        )
        nodes[follower_id] = restarted_node
        transports[follower_id] = restarted_transport
        state_machines[follower_id] = restarted_state_machine
        runtimes[follower_id] = restarted_runtime
        restarted_runtime.start()

        assert _wait_until(
            lambda: (
                restarted_node.commit_index == 3
                and restarted_node.last_applied == 3
                and nodes["node-1"].get_status()["replicationProgress"][
                    follower_id
                ]["matchIndex"] == 3
            )
        )
        follower_progress = nodes["node-1"].get_status()[
            "replicationProgress"
        ][follower_id]
        assert follower_progress["nextIndex"] == 4
        assert follower_progress["ackStatus"] == "ACKNOWLEDGED"
        assert [
            command["commandId"]
            for command in restarted_state_machine.commands
        ] == ["isolated-booking-2", "isolated-booking-3"]

        runtimes["node-1"].stop()

        replacement = nodes["node-2"]
        assert replacement.start_election(transports["node-2"].request_vote)
        assert replacement.state == RaftNode.LEADER
        assert len(replacement.votes_received) >= 4
        assert _wait_until(
            lambda: (
                nodes["node-1"].current_term == replacement.current_term
                and nodes["node-1"].state == RaftNode.FOLLOWER
                and nodes["node-1"].leader_id == "node-2"
            )
        )
        assert nodes["node-1"].state == RaftNode.FOLLOWER
        assert nodes["node-1"].leader_id == "node-2"

        runtimes["node-1"] = RaftRuntime(
            nodes["node-1"],
            transports["node-1"],
            state_machines["node-1"],
        )
        runtimes["node-1"].start()

        replacement_response = _submit_command(
            addresses["node-2"],
            "isolated-booking-4",
            "booking-4",
        )

        assert replacement_response.success is True
        assert replacement_response.committed is True
        assert _wait_until(
            lambda: all(
                node.commit_index == 4 and node.last_applied == 4
                for node in nodes.values()
            )
        )

        for node_id in ("node-3", "node-4", "node-5"):
            _stop_member(node_id, runtimes, transports)

        four_node_response = _submit_command(
            addresses["node-2"],
            "isolated-booking-5",
            "booking-5",
        )
        assert four_node_response.success is True
        assert four_node_response.committed is True
        assert _wait_until(
            lambda: all(
                nodes[node_id].commit_index == 5
                and nodes[node_id].last_applied == 5
                for node_id in ("node-1", "node-2", "node-6", "node-7")
            )
        )

        _stop_member("node-6", runtimes, transports)
        failed_quorum_submission = nodes["node-2"].submit_command(
            "isolated-booking-6",
            "TEST_BOOKING",
            {"bookingId": "booking-6"},
        )
        assert failed_quorum_submission["success"] is True
        runtimes["node-2"]._replicate_to_followers()
        assert nodes["node-2"].commit_index == 5
        assert not nodes["node-2"].wait_for_commit(
            failed_quorum_submission["index"],
            timeout=0.1,
        )
    finally:
        for runtime in runtimes.values():
            runtime.stop()
        for transport in transports.values():
            if transport is not None:
                transport.close()
