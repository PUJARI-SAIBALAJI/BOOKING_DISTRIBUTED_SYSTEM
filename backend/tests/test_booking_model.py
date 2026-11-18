import pytest

from bson import ObjectId

from backend.models.booking import Booking


def sample_booking():

    return {

        "userId": ObjectId(),

        "eventId": ObjectId(),

        "seats": [
            ObjectId(),
            ObjectId()
        ],

        "totalAmount": 3000,

        "reservationId": "RES123",

        "bookingReference": "FR-2026-001",

        "paymentId": None,

        "refundId": None,

        "status": "pending"
    }


def test_valid_booking():

    assert Booking.validate(sample_booking()) is True


def test_missing_user_id():

    data = sample_booking()

    del data["userId"]

    with pytest.raises(ValueError):

        Booking.validate(data)


def test_missing_event_id():

    data = sample_booking()

    del data["eventId"]

    with pytest.raises(ValueError):

        Booking.validate(data)


def test_negative_total_amount():

    data = sample_booking()

    data["totalAmount"] = -100

    with pytest.raises(ValueError):

        Booking.validate(data)


def test_invalid_status():

    data = sample_booking()

    data["status"] = "processing"

    with pytest.raises(ValueError):

        Booking.validate(data)


def test_invalid_seat_id():

    data = sample_booking()

    data["seats"] = ["invalid-id"]

    with pytest.raises(ValueError):

        Booking.validate(data)


def test_default_status():

    data = sample_booking()

    del data["status"]

    document = Booking.prepare(data)

    assert document["status"] == "pending"


def test_object_id_conversion():

    data = sample_booking()

    data["userId"] = str(data["userId"])

    document = Booking.prepare(data)

    assert isinstance(
        document["userId"],
        ObjectId
    )


def test_booking_reference():

    data = sample_booking()

    document = Booking.prepare(data)

    assert document["bookingReference"] == "FR-2026-001"