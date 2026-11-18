import pytest

from backend.config import Settings, _integer_compat
from frontend.utils.operating_mode import (
    NORMAL_MODE,
    RAFT_MODE,
    api_base_url,
    configured_raft_nodes,
)


def test_raft_node_requires_its_own_mongo_uri(monkeypatch):
    monkeypatch.delenv("RAFT_NODE_1_MONGO_URI", raising=False)
    monkeypatch.setenv("MONGODB_URI", "mongodb://standalone.example/")

    with pytest.raises(ValueError, match="never fall back"):
        Settings.raft_mongo_uri("node-1")


def test_raft_node_uses_its_configured_database_uri(monkeypatch):
    monkeypatch.setenv(
        "RAFT_NODE_1_MONGO_URI",
        "mongodb://raft-node-1.example/",
    )

    assert Settings.raft_mongo_uri("node-1") == "mongodb://raft-node-1.example/"


def test_frontend_accepts_any_odd_cluster_size():
    nodes = configured_raft_nodes(
        5,
        {
            f"RAFT_NODE_{index}_API_URL": f"http://node-{index}:50{index}"
            for index in range(1, 6)
        },
    )

    assert len(nodes) == 5
    assert nodes[-1] == ("node-5", "http://node-5:505")


def test_frontend_rejects_even_cluster_size():
    with pytest.raises(ValueError, match="odd integer"):
        configured_raft_nodes(4, {})


def test_port_setting_prefers_port_and_keeps_app_port_compatibility(monkeypatch):
    monkeypatch.setenv("PORT", "5100")
    monkeypatch.setenv("APP_PORT", "5200")
    assert _integer_compat("PORT", "APP_PORT", 5000) == 5100

    monkeypatch.delenv("PORT")
    assert _integer_compat("PORT", "APP_PORT", 5000) == 5200


def test_normal_api_url_accepts_api_base_url():
    assert api_base_url(
        NORMAL_MODE,
        {"API_BASE_URL": "http://api.example:5000/"},
    ) == "http://api.example:5000"


def test_raft_gateway_defaults_to_normal_rest_base_url():
    assert api_base_url(
        RAFT_MODE,
        {"API_BASE_URL": "http://api.example:5000/"},
    ) == "http://api.example:5000"


def test_raft_gateway_accepts_dedicated_base_url():
    assert api_base_url(
        RAFT_MODE,
        {
            "API_BASE_URL": "http://normal.example:5000",
            "RAFT_API_BASE_URL": "http://gateway.example:5050/",
        },
    ) == "http://gateway.example:5050"
