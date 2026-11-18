import smtplib
from unittest.mock import Mock, patch

import pytest

from backend.services.notification_service import NotificationError, NotificationService


@pytest.fixture
def booking():
    return {
        "id": "booking-1",
        "status": "confirmed",
        "bookingReference": "FR-TEST",
        "totalAmount": 100,
        "event": {"title": "Test event", "date": "2027-01-01", "time": "10:00", "venue": "Hall"},
        "seats": [{"seatNumber": "A1"}],
    }


@pytest.fixture
def user():
    return {"email": "customer@example.test", "name": "Customer"}


def test_enqueue_is_idempotent_and_records_booking_details(booking, user):
    collection = Mock()
    service = NotificationService({"notificationoutbox": collection})
    service.enqueue("normal", "confirmation", user, booking)
    service.enqueue("normal", "confirmation", user, booking)

    calls = collection.update_one.call_args_list
    assert len(calls) == 2
    assert calls[0].args[0] == {"_id": "normal:booking-1:confirmation"}
    document = calls[0].args[1]["$setOnInsert"]
    assert document["recipient"] == user["email"]
    assert document["seats"] == ["A1"]
    assert document["reference"] == "FR-TEST"
    assert all(call.kwargs["upsert"] for call in calls)


def test_enqueue_requires_confirmed_booking_and_complete_details(booking, user):
    service = NotificationService({"notificationoutbox": Mock()})
    booking["status"] = "pending"
    with pytest.raises(NotificationError):
        service.enqueue("normal", "confirmation", user, booking)
    booking["status"] = "confirmed"
    booking["seats"] = []
    with pytest.raises(NotificationError):
        service.enqueue("normal", "confirmation", user, booking)


def _queued_item(booking, user):
    collection = Mock()
    service = NotificationService({"notificationoutbox": collection})
    service.enqueue("normal", "confirmation", user, booking)
    item = collection.update_one.call_args.args[1]["$setOnInsert"]
    item["attempts"] = 1
    collection.reset_mock()
    collection.update_many.return_value.modified_count = 0
    collection.find_one_and_update.return_value = item
    return service, collection


@patch("backend.services.notification_service.settings")
@patch("backend.services.notification_service.smtplib.SMTP")
def test_smtp_acceptance_marks_sent_and_contains_details(smtp_class, settings, booking, user):
    settings.SMTP_HOST = "smtp.example.test"
    settings.SMTP_PORT = 587
    settings.SMTP_USER = "sender@example.test"
    settings.SMTP_PASSWORD = "not-a-real-password"
    settings.SMTP_FROM_NAME = "FlashReserve"
    service, collection = _queued_item(booking, user)

    assert service.process_one()
    message = smtp_class.return_value.send_message.call_args.args[0]
    assert message["To"] == user["email"]
    assert "FR-TEST" in message.get_content()
    assert "A1" in message.get_content()
    assert collection.update_one.call_args.args[1]["$set"]["status"] == "sent"


@pytest.mark.parametrize("failure_point,expected", [("login", "pending"), ("send_message", "delivery_unknown")])
@patch("backend.services.notification_service.settings")
@patch("backend.services.notification_service.smtplib.SMTP")
def test_retry_only_when_delivery_outcome_is_known(
    smtp_class, settings, failure_point, expected, booking, user
):
    settings.SMTP_HOST = "smtp.example.test"
    settings.SMTP_PORT = 587
    settings.SMTP_USER = "sender@example.test"
    settings.SMTP_PASSWORD = "not-a-real-password"
    settings.SMTP_FROM_NAME = "FlashReserve"
    getattr(smtp_class.return_value, failure_point).side_effect = smtplib.SMTPServerDisconnected()
    service, collection = _queued_item(booking, user)

    assert service.process_one()
    assert collection.update_one.call_args.args[1]["$set"]["status"] == expected


def test_expired_sending_attempt_is_marked_unknown_not_resent():
    collection = Mock()
    collection.update_many.return_value.modified_count = 1
    collection.find_one_and_update.return_value = None
    service = NotificationService({"notificationoutbox": collection})

    assert not service.process_one()
    assert collection.update_many.call_args.args[1]["$set"]["status"] == "delivery_unknown"
    assert collection.find_one_and_update.call_args.args[0]["status"] == "pending"


@patch("backend.services.notification_service.settings")
@patch("backend.services.notification_service.smtplib.SMTP")
def test_smtp_explicit_rejection_is_retried(smtp_class, settings, booking, user):
    settings.SMTP_HOST = "smtp.example.test"
    settings.SMTP_PORT = 587
    settings.SMTP_USER = "sender@example.test"
    settings.SMTP_PASSWORD = "not-a-real-password"
    settings.SMTP_FROM_NAME = "FlashReserve"
    smtp_class.return_value.send_message.side_effect = smtplib.SMTPDataError(451, b"Try later")
    service, collection = _queued_item(booking, user)

    service.process_one()
    assert collection.update_one.call_args.args[1]["$set"]["status"] == "pending"


@patch("backend.services.notification_service.settings")
def test_cancellation_message_contains_reference_and_seats(settings, booking, user):
    settings.SMTP_USER = "sender@example.test"
    settings.SMTP_FROM_NAME = "FlashReserve"
    booking["status"] = "cancelled"
    collection = Mock()
    service = NotificationService({"notificationoutbox": collection})
    service.enqueue("raft", "cancellation", user, booking)
    item = collection.update_one.call_args.args[1]["$setOnInsert"]

    message = service._message(item)
    assert "cancelled" in message["Subject"]
    assert "FR-TEST" in message.get_content()
    assert "A1" in message.get_content()
