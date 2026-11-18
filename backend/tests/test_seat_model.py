import pytest

from bson import ObjectId

from backend.models.seat import Seat


def sample_seat():

    return {
        "eventId": ObjectId(),
        "seatNumber": "A1",
        "category": "Gold",
        "status": "available"
    }


def test_valid_seat():

    assert Seat.validate(sample_seat()) is True


def test_missing_event_id():

    data = sample_seat()

    del data["eventId"]

    with pytest.raises(ValueError):

        Seat.validate(data)


def test_missing_seat_number():

    data = sample_seat()

    del data["seatNumber"]

    with pytest.raises(ValueError):

        Seat.validate(data)


def test_invalid_category():

    data = sample_seat()

    data["category"] = "Diamond"

    with pytest.raises(ValueError):

        Seat.validate(data)


def test_invalid_status():

    data = sample_seat()

    data["status"] = "cancelled"

    with pytest.raises(ValueError):

        Seat.validate(data)


def test_default_status():

    data = sample_seat()

    del data["status"]

    document = Seat.prepare(data)

    assert document["status"] == "available"


def test_object_id_conversion():

    data = sample_seat()

    data["eventId"] = str(data["eventId"])

    document = Seat.prepare(data)

    assert isinstance(
        document["eventId"],
        ObjectId
    )