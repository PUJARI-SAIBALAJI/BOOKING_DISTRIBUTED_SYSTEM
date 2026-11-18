from types import SimpleNamespace
from unittest.mock import Mock, patch

from fastapi.testclient import TestClient
from bson import ObjectId

from backend.api import _current_user, _serialize_booking, create_app
from backend.raft.http_gateway import RaftGatewayError
from backend.services.notification_service import NotificationError
from frontend.utils import api as frontend_api
from frontend.utils.operating_mode import NORMAL_MODE, RAFT_MODE


class FakeCollection:
    def create_index(self, *args, **kwargs):
        return "fake-index"


class FakeDatabase:
    name = "test-database"
    client = SimpleNamespace(
        admin=SimpleNamespace(command=lambda name: {"ok": 1})
    )

    def __getitem__(self, _name):
        return FakeCollection()


class FakeMongo:
    def __init__(self):
        self.database = FakeDatabase()
        self.closed = False

    def connect(self):
        return self.database

    def close(self):
        self.closed = True


@patch("backend.api.NotificationService")
def test_health_route_reports_the_standalone_database(notifications):
    mongo = FakeMongo()

    with TestClient(create_app(mongo)) as client:
        response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "data": {
            "status": "ok",
            "raftEnabled": False,
            "database": {
                "connected": True,
                "name": "test-database",
            },
        },
    }
    assert mongo.closed


def test_frontend_sends_the_bearer_token():
    response = Mock(
        ok=True,
        status_code=200,
        json=Mock(return_value={"success": True, "data": {"ok": True}}),
    )
    session = SimpleNamespace(
        session_state={"operating_mode": NORMAL_MODE}
    )

    with patch.object(frontend_api, "st", session):
        with patch.object(frontend_api.requests, "request", return_value=response) as request:
            result = frontend_api._request_impl(
                "GET",
                "/api/bookings",
                token="test-token",
            )

    assert result == {"ok": True}
    assert request.call_args.kwargs["headers"]["Authorization"] == "Bearer test-token"


def test_frontend_chat_normalizes_backend_answer_for_support_page():
    with patch.object(
        frontend_api,
        "_request",
        return_value={"answer": "Hi! How can I help?", "status": "fallback"},
    ) as request:
        result = frontend_api.ask_chat(
            "Hi",
            "test-token",
            event_id="event-1",
            history=[{"role": "user", "content": "Hello"}],
        )

    assert result == {
        "answer": "Hi! How can I help?",
        "response": "Hi! How can I help?",
        "status": "fallback",
    }
    request.assert_called_once_with(
        "POST",
        "/api/chat",
        token="test-token",
        payload={
            "message": "Hi",
            "history": [{"role": "user", "content": "Hello"}],
            "eventId": "event-1",
        },
        timeout=35,
    )


def test_frontend_chat_preserves_response_backend_contract():
    backend_result = {"response": "Already normalized.", "status": "ok"}
    with patch.object(frontend_api, "_request", return_value=backend_result):
        result = frontend_api.ask_chat("Hi", "test-token")

    assert result is backend_result


def test_frontend_health_check_accepts_the_live_backend_response_shape():
    response = Mock(
        status_code=200,
        json=Mock(return_value={
            "success": True,
            "data": {
                "status": "ok",
                "raftEnabled": False,
                "database": {"connected": True, "name": "flashreserve"},
            },
        }),
    )
    with patch.object(
        frontend_api,
        "api_base_url",
        return_value="http://127.0.0.1:5000",
    ):
        with patch.object(frontend_api.requests, "get", return_value=response) as request:
            with patch.object(frontend_api, "get_raft_cluster_status", return_value=[]):
                result = frontend_api.get_mode_availability(timeout=2)

    assert request.call_args.args[0] == "http://127.0.0.1:5000/api/health"
    assert result[NORMAL_MODE]["available"] is True
    assert "flashreserve" in result[NORMAL_MODE]["reason"]


def test_frontend_health_check_reports_connection_failure_and_can_retry():
    with patch.object(
        frontend_api,
        "api_base_url",
        return_value="http://127.0.0.1:5000",
    ):
        with patch.object(
            frontend_api.requests,
            "get",
            side_effect=frontend_api.requests.ConnectionError,
        ):
            with patch.object(frontend_api, "get_raft_cluster_status", return_value=[]):
                result = frontend_api.get_mode_availability(timeout=2)

    assert result[NORMAL_MODE]["available"] is False
    assert result[NORMAL_MODE]["reason"] == (
        "Could not connect to backend at http://127.0.0.1:5000/api/health."
    )


def test_rest_app_registers_all_normal_mode_contract_routes():
    mongo = FakeMongo()
    app = create_app(mongo)
    paths = {route.path for route in app.routes}

    assert {
        "/api/health",
        "/api/auth/register",
        "/api/auth/login",
        "/api/events",
        "/api/events/{event_id}",
        "/api/events/{event_id}/seats",
        "/api/events/{event_id}/seats/reserve",
        "/api/bookings",
        "/api/bookings/{booking_id}/cancel",
        "/api/payments/mock",
        "/api/chat",
        "/api/admin/stats",
        "/api/admin/users",
        "/api/admin/bookings",
        "/api/admin/events",
        "/api/admin/events/{event_id}",
        "/api/admin/events/{event_id}/seats",
        "/api/admin/seats/{seat_id}",
    } <= paths


def test_rest_app_registers_raft_gateway_and_booking_routes():
    app = create_app(FakeMongo())
    paths = {route.path for route in app.routes}

    assert {
        "/api/raft/status",
        "/api/raft/leader",
        "/api/raft/nodes",
        "/api/raft/log-status",
        "/api/raft/events",
        "/api/raft/events/{event_id}",
        "/api/raft/events/{event_id}/seats",
        "/api/raft/events/{event_id}/seats/reserve",
        "/api/raft/bookings",
        "/api/raft/bookings/{booking_id}",
        "/api/raft/bookings/{booking_id}/cancel",
        "/api/raft/payments/mock",
        "/api/raft/chat",
        "/api/raft/admin/stats",
        "/api/raft/admin/users",
        "/api/raft/admin/bookings",
        "/api/raft/admin/events",
        "/api/raft/admin/events/{event_id}",
        "/api/raft/admin/events/{event_id}/seats",
        "/api/raft/admin/seats/{seat_id}",
    } <= paths


@patch("backend.api.NotificationService")
@patch("backend.api.EventService")
@patch("backend.api.RaftHttpGateway")
def test_raft_event_catalog_reads_only_the_raft_database(
    gateway_class,
    event_service,
    _notifications,
):
    mongo = FakeMongo()
    raft_database = object()
    event = {"_id": ObjectId(), "title": "Raft-only event"}
    gateway = gateway_class.return_value
    gateway.read_database.return_value = raft_database
    event_service.return_value.get_all_events.return_value = [event]

    with TestClient(create_app(mongo)) as client:
        response = client.get("/api/raft/events")

    assert response.status_code == 200
    assert response.json()["data"][0]["title"] == "Raft-only event"
    event_service.assert_called_once_with(raft_database)
    gateway.read_database.assert_called_once_with()
    gateway.submit_command.assert_not_called()


@patch("backend.api.NotificationService")
@patch("backend.api.RaftHttpGateway")
def test_raft_admin_event_catalog_reads_only_the_raft_database(
    gateway_class,
    _notifications,
):
    mongo = FakeMongo()
    event = {"_id": ObjectId(), "title": "Raft admin event"}
    cursor = Mock()
    cursor.sort.return_value = [event]
    events_collection = Mock()
    events_collection.find.return_value = cursor
    raft_database = {"events": events_collection}
    gateway = gateway_class.return_value
    gateway.read_database.return_value = raft_database

    app = create_app(mongo)
    app.dependency_overrides[_current_user] = lambda: {
        "_id": ObjectId(),
        "role": "admin",
    }
    with TestClient(app) as client:
        response = client.get("/api/raft/admin/events")

    assert response.status_code == 200
    assert response.json()["data"][0]["title"] == "Raft admin event"
    gateway.read_database.assert_called_once_with()
    gateway.submit_command.assert_not_called()
    events_collection.find.assert_called_once_with()


def test_raft_mode_routes_booking_requests_through_gateway_prefix():
    response = Mock(
        ok=True,
        status_code=200,
        json=Mock(return_value={"success": True, "data": {"id": "booking-1"}}),
    )
    session = SimpleNamespace(session_state={"operating_mode": RAFT_MODE})

    with patch.object(frontend_api, "st", session):
        with patch.object(frontend_api, "get_api_base_url", return_value="http://gateway"):
            with patch.object(frontend_api.requests, "request", return_value=response) as request:
                result = frontend_api._request_impl(
                    "POST",
                    "/api/bookings",
                    token="test-token",
                    payload={"reservationId": "reservation-1"},
                )

    assert result == {"id": "booking-1"}
    assert request.call_args.args[1] == "http://gateway/api/raft/bookings"


def test_raft_mode_keeps_shared_login_endpoint():
    response = Mock(
        ok=True,
        status_code=200,
        json=Mock(return_value={"success": True, "data": {"token": "token"}}),
    )
    session = SimpleNamespace(session_state={"operating_mode": RAFT_MODE})

    with patch.object(frontend_api, "st", session):
        with patch.object(frontend_api, "get_api_base_url", return_value="http://gateway"):
            with patch.object(frontend_api.requests, "request", return_value=response) as request:
                frontend_api._request_impl(
                    "POST",
                    "/api/auth/login",
                    payload={"email": "user@example.test", "password": "password"},
                )

    assert request.call_args.args[1] == "http://gateway/api/auth/login"


@patch("backend.api.NotificationService")
def test_missing_upload_directory_is_created_and_missing_image_returns_404(notifications, tmp_path):
    upload_dir = tmp_path / "pictures" / "uploads"
    with patch("backend.api.UPLOAD_DIR", upload_dir):
        with TestClient(create_app(FakeMongo())) as client:
            assert client.get("/uploads/missing.png").status_code == 404
    assert upload_dir.is_dir()


def test_serialization_resolves_raft_string_object_ids():
    event_id, seat_id, payment_id, refund_id = (ObjectId() for _ in range(4))
    collections = {name: Mock() for name in ("events", "seats", "payments", "refunds")}
    collections["events"].find_one.return_value = {"_id": event_id}
    collections["seats"].find.return_value = [{"_id": seat_id, "seatNumber": "A1"}]
    booking = {
        "eventId": str(event_id), "seats": [str(seat_id)],
        "paymentId": str(payment_id), "refundId": str(refund_id),
    }

    result = _serialize_booking(collections, booking)
    assert result["seats"][0]["seatNumber"] == "A1"
    collections["seats"].find.assert_called_once_with({"_id": {"$in": [seat_id]}})
    collections["payments"].find_one.assert_called_once_with({"_id": payment_id})
    collections["refunds"].find_one.assert_called_once_with({"_id": refund_id})


@patch("backend.api.NotificationService")
@patch("backend.api._serialize_booking")
@patch("backend.api.PaymentService")
def test_normal_payment_enqueues_only_confirmed_success(payment_service, serialize, notifications):
    user = {"_id": ObjectId(), "email": "customer@example.test"}
    booking = {"id": str(ObjectId()), "status": "confirmed"}
    serialize.return_value = booking
    service = payment_service.return_value
    service.process_mock_payment.return_value = {"payment": {"status": "success"}, "booking": {}}
    # A nonempty booking is required by the route.
    service.process_mock_payment.return_value["booking"] = {"_id": ObjectId()}
    app = create_app(FakeMongo())
    app.dependency_overrides[_current_user] = lambda: user
    with TestClient(app) as client:
        response = client.post("/api/payments/mock", json={})
        assert response.status_code == 200
        notifications.return_value.enqueue.assert_called_once_with(
            "normal", "confirmation", user, booking
        )
        notifications.return_value.enqueue.reset_mock()
        service.process_mock_payment.return_value = {
            "payment": {"status": "failed"}, "booking": {"_id": ObjectId()}
        }
        assert client.post("/api/payments/mock", json={}).status_code == 200
        notifications.return_value.enqueue.assert_not_called()


@patch("backend.api.NotificationService")
@patch("backend.api._serialize_booking")
@patch("backend.api.RaftHttpGateway")
def test_raft_payment_does_not_notify_uncommitted_commands(gateway_class, serialize, notifications):
    user = {"_id": ObjectId(), "email": "customer@example.test"}
    app = create_app(FakeMongo())
    app.dependency_overrides[_current_user] = lambda: user
    gateway = gateway_class.return_value
    gateway.submit_command.side_effect = RaftGatewayError("No quorum", 503, "RAFT_NO_QUORUM")
    with TestClient(app) as client:
        response = client.post("/api/raft/payments/mock", json={"idempotencyKey": "test"})
        assert response.status_code == 503
        notifications.return_value.enqueue.assert_not_called()
        gateway.submit_command.side_effect = None
        gateway.submit_command.return_value = {
            "leaderId": "node-1",
            "result": {"result": {"payment": {"status": "success"}, "booking": {"_id": "id"}}},
        }
        booking = {"id": "id", "status": "confirmed"}
        serialize.return_value = booking
        response = client.post("/api/raft/payments/mock", json={"idempotencyKey": "test"})
        assert response.status_code == 200
        notifications.return_value.enqueue.assert_called_once_with(
            "raft", "confirmation", user, booking
        )


@patch("backend.api.NotificationService")
@patch("backend.api._serialize_booking")
@patch("backend.api.BookingLifecycleService")
def test_normal_cancellation_enqueues_and_surfaces_queue_error(lifecycle, serialize, notifications):
    user = {"_id": ObjectId(), "email": "customer@example.test"}
    booking_id = str(ObjectId())
    cancelled = {"id": booking_id, "status": "cancelled"}
    lifecycle.return_value.cancel_booking.return_value = {"_id": ObjectId()}
    serialize.return_value = cancelled
    app = create_app(FakeMongo())
    app.dependency_overrides[_current_user] = lambda: user
    with TestClient(app) as client:
        response = client.put(f"/api/bookings/{booking_id}/cancel")
        assert response.status_code == 200
        notifications.return_value.enqueue.assert_called_once_with(
            "normal", "cancellation", user, cancelled
        )
        notifications.return_value.enqueue.side_effect = NotificationError("test failure")
        response = client.put(f"/api/bookings/{booking_id}/cancel")
        assert response.status_code == 503
        assert "operation completed" in response.json()["message"]


@patch("backend.api.NotificationService")
@patch("backend.api._serialize_booking")
@patch("backend.api.RaftHttpGateway")
def test_raft_cancellation_enqueues_only_after_commit(gateway_class, serialize, notifications):
    user = {"_id": ObjectId(), "email": "customer@example.test"}
    booking_id = str(ObjectId())
    gateway = gateway_class.return_value
    gateway.submit_command.side_effect = RaftGatewayError("No quorum", 503, "RAFT_NO_QUORUM")
    app = create_app(FakeMongo())
    app.dependency_overrides[_current_user] = lambda: user
    with TestClient(app) as client:
        response = client.put(f"/api/raft/bookings/{booking_id}/cancel")
        assert response.status_code == 503
        notifications.return_value.enqueue.assert_not_called()
        gateway.submit_command.side_effect = None
        gateway.submit_command.return_value = {
            "leaderId": "node-1", "result": {"result": {"result": {"_id": booking_id}}}
        }
        cancelled = {"id": booking_id, "status": "cancelled"}
        serialize.return_value = cancelled
        response = client.put(f"/api/raft/bookings/{booking_id}/cancel")
        assert response.status_code == 200
        notifications.return_value.enqueue.assert_called_once_with(
            "raft", "cancellation", user, cancelled
        )
