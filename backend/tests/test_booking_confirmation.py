import pytest

from datetime import datetime, timezone

from bson import ObjectId

from backend.models.booking_confirmation import BookingConfirmation


def sample_confirmation():

    return {
        "bookingId": ObjectId(),
        "bookingReference": "FR-2026-001",
        "messageId": "MSG-001",
        "recipientEmail": "customer@example.com",
        "customerName": "Santosh",
        "eventName": "IPL Final",
        "eventDate": "2026-11-20",
        "eventTime": "7:30 PM",
        "venue": "Hyderabad Stadium",
        "seats": ["A1", "A2"],
        "ticketQuantity": 2,
        "ticketPrice": 1500,
        "totalAmount": 3000,
        "paymentStatus": "paid",
        "confirmedAt": datetime.now(timezone.utc)
    }


def test_valid_confirmation():

    assert BookingConfirmation.validate(
        sample_confirmation()
    ) is True


def test_missing_booking_id():

    data = sample_confirmation()

    del data["bookingId"]

    with pytest.raises(ValueError):

        BookingConfirmation.validate(data)


def test_invalid_booking_id():

    data = sample_confirmation()

    data["bookingId"] = "invalid-id"

    with pytest.raises(ValueError):

        BookingConfirmation.validate(data)


def test_invalid_status():

    data = sample_confirmation()

    data["status"] = "processing"

    with pytest.raises(ValueError):

        BookingConfirmation.validate(data)


def test_invalid_delivery_outcome():

    data = sample_confirmation()

    data["deliveryAttempts"] = [{
        "attemptId": "ATT-1",
        "claimedAt": datetime.now(timezone.utc),
        "outcome": "unknown_status"
    }]

    with pytest.raises(ValueError):

        BookingConfirmation.validate(data)


def test_valid_delivery_attempt():

    data = sample_confirmation()

    data["deliveryAttempts"] = [{
        "attemptId": "ATT-1",
        "claimedAt": datetime.now(timezone.utc),
        "outcome": "claimed"
    }]

    assert BookingConfirmation.validate(data) is True


def test_default_confirmation_status():

    document = BookingConfirmation.prepare(
        sample_confirmation()
    )

    assert document["status"] == "pending"


def test_default_delivery_attempts():

    document = BookingConfirmation.prepare(
        sample_confirmation()
    )

    assert document["deliveryAttempts"] == []


def test_cancellation_optional():

    document = BookingConfirmation.prepare(
        sample_confirmation()
    )

    assert "cancellation" not in document


def test_object_id_conversion():

    data = sample_confirmation()

    data["bookingId"] = str(data["bookingId"])

    document = BookingConfirmation.prepare(data)

    assert isinstance(document["bookingId"], ObjectId)