import pytest

from datetime import datetime, timezone

from backend.models.event import Event


def sample_event():

    return {
        "title": "IPL Final",
        "category": "Sports",
        "venue": "Hyderabad Stadium",
        "date": datetime.now(timezone.utc),
        "time": "7:30 PM",
        "description": "Cricket Final",
        "totalSeats": 500,
        "seatsPerRow": 10,
        "price": 1500,
        "status": "active",
        "posterUrl": "ipl.jpg"
    }


def test_valid_event():

    assert Event.validate(sample_event()) is True


def test_missing_title():

    data = sample_event()

    del data["title"]

    with pytest.raises(ValueError):

        Event.validate(data)


def test_negative_price():

    data = sample_event()

    data["price"] = -100

    with pytest.raises(ValueError):

        Event.validate(data)


def test_invalid_status():

    data = sample_event()

    data["status"] = "completed"

    with pytest.raises(ValueError):

        Event.validate(data)


def test_default_seats_per_row():

    data = sample_event()

    del data["seatsPerRow"]

    document = Event.prepare(data)

    assert document["seatsPerRow"] == 10


def test_default_status():

    data = sample_event()

    del data["status"]

    document = Event.prepare(data)

    assert document["status"] == "active"