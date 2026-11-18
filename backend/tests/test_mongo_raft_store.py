from backend.raft.mongo_raft_store import MongoRaftStore


class FakeCollection:

    def __init__(self):
        self.documents = {}

    def with_options(self, **kwargs):
        return self

    def create_index(self, *args, **kwargs):
        return "fake-index"

    def find_one(self, query):
        return self.documents.get(query["_id"])

    def find(self, query):
        return FakeCursor([
            item for item in self.documents.values()
            if item.get("nodeId") == query["nodeId"]
        ])

    def bulk_write(self, operations, ordered=True):

        for operation in operations:

            request = operation._filter
            document = operation._doc["$set"]

            self.documents[
                (request["nodeId"], request.get("index",
                 request.get("requestId")))
            ] = document

    def delete_many(self, query):

        node_id = query["nodeId"]
        maximum = query["index"]["$gt"]

        keys = [
            key for key, document in self.documents.items()
            if document["nodeId"] == node_id
            and document["index"] > maximum
        ]

        for key in keys:
            del self.documents[key]

    def update_one(self, query, update, upsert=False):

        self.documents[query["_id"]] = {
            "_id": query["_id"],
            **update["$set"]
        }


class FakeCursor(list):

    def sort(self, field, direction):
        return FakeCursor(
            sorted(self, key=lambda item: item[field])
        )


class FakeDatabase:

    def __init__(self):

        self.collections = {
            "raftstates": FakeCollection(),
            "raftlogentries": FakeCollection(),
            "raftappliedresults": FakeCollection()
        }

    def __getitem__(self, name):
        return self.collections[name]


def sample_state():

    return {
        "clusterId": "test-cluster",
        "clusterConfigVersion": 1,
        "configuration": {
            "oldMembers": [
                "node-1",
                "node-2",
                "node-3"
            ],
            "newMembers": None,
            "index": 0
        },
        "currentTerm": 2,
        "votedFor": "node-1",
        "log": [
            {
                "index": 1,
                "term": 1,
                "requestId": "request-1",
                "command": {
                    "type": "test.command"
                }
            }
        ],
        "commitIndex": 1,
        "lastApplied": 1,
        "appliedResults": [
            {
                "index": 1,
                "requestId": "request-1",
                "result": {
                    "ok": True
                }
            }
        ]
    }


def test_initial_load_returns_none():

    database = FakeDatabase()

    store = MongoRaftStore(database)

    assert store.load("node-1") is None


def test_save_and_load_state():

    database = FakeDatabase()

    store = MongoRaftStore(database)

    state = sample_state()

    store.save("node-1", state)

    loaded = store.load("node-1")

    assert loaded["clusterId"] == "test-cluster"
    assert loaded["currentTerm"] == 2
    assert loaded["votedFor"] == "node-1"
    assert loaded["commitIndex"] == 1
    assert loaded["lastApplied"] == 1


def test_log_entries_are_persisted():

    database = FakeDatabase()

    store = MongoRaftStore(database)

    store.save("node-1", sample_state())

    loaded = store.load("node-1")

    assert len(loaded["log"]) == 1

    assert loaded["log"][0]["requestId"] == "request-1"


def test_applied_results_are_persisted():

    database = FakeDatabase()

    store = MongoRaftStore(database)

    store.save("node-1", sample_state())

    loaded = store.load("node-1")

    assert len(loaded["appliedResults"]) == 1

    assert loaded["appliedResults"][0]["result"]["ok"] is True


def test_seven_nodes_use_separate_state_records():

    database = FakeDatabase()

    store = MongoRaftStore(database)

    for index in range(1, 8):

        state = sample_state()

        state["clusterId"] = "test-cluster"

        store.save(
            f"node-{index}",
            state
        )

    assert len(database["raftstates"].documents) == 7