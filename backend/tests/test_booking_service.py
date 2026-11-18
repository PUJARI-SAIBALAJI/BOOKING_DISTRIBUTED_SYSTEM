import pytest

from bson import ObjectId
from unittest.mock import Mock

from backend.services.booking_service import (
    BookingService,
    BookingError,
)


def test_generate_booking_reference():

    reference = BookingService.generate_reference()

    assert reference.startswith("FR-")
    assert len(reference) == 15


def test_normalize_seats():

    result = BookingService.normalize_seats(
        ["A1", "A2"]
    )

    assert result == ["A1", "A2"]


def test_empty_seat_selection():

    with pytest.raises(BookingError):
        BookingService.normalize_seats([])


def test_more_than_20_seats():

    seats = [f"A{i}" for i in range(21)]

    with pytest.raises(BookingError):
        BookingService.normalize_seats(seats)


def test_duplicate_seats():

    with pytest.raises(BookingError):
        BookingService.normalize_seats(
            ["A1", "A1"]
        )


def test_invalid_seat_number():

    with pytest.raises(BookingError):
        BookingService.normalize_seats(
            ["A1", ""]
        )


def test_invalid_user_id():

    service = BookingService(None)

    with pytest.raises(BookingError):
        service.create_booking(
            "invalid",
            str(ObjectId()),
            ["A1"],
            500,
        )


def test_invalid_event_id():

    service = BookingService(None)

    with pytest.raises(BookingError):
        service.create_booking(
            str(ObjectId()),
            "invalid",
            ["A1"],
            500,
        )


def test_invalid_total_amount():

    service = BookingService(None)

    with pytest.raises(BookingError):
        service.create_booking(
            str(ObjectId()),
            str(ObjectId()),
            ["A1"],
            -100,
        )


def test_booking_reference_uniqueness():

    references = {
        BookingService.generate_reference()
        for _ in range(100)
    }

    assert len(references) == 100


def test_request_id_generation():

    user_id = str(ObjectId())

    first = BookingService.generate_request_id(
        user_id,
        "reservation-1"
    )

    second = BookingService.generate_request_id(
        user_id,
        "reservation-1"
    )

    assert first == second


def test_existing_booking_matches_stored_seat_ids():
    event_id = ObjectId()
    seat_ids = [ObjectId(), ObjectId()]
    seats = Mock()
    seats.find.return_value = [
        {"_id": seat_ids[0], "seatNumber": "A1"},
        {"_id": seat_ids[1], "seatNumber": "A2"},
    ]
    service = BookingService({"seats": seats})
    booking = {"eventId": event_id, "totalAmount": 100, "seats": seat_ids}

    assert service.matches_booking(booking, event_id, ["A2", "A1"], 100)
    assert not service.matches_booking(booking, event_id, ["A1", "A3"], 100)
    seats.find.assert_called_with({
        "_id": {"$in": seat_ids},
        "eventId": event_id,
    })


def test_existing_booking_rejects_missing_or_duplicate_seat_ids():
    event_id = ObjectId()
    seat_id = ObjectId()
    seats = Mock()
    seats.find.return_value = []
    service = BookingService({"seats": seats})
    booking = {"eventId": event_id, "totalAmount": 100, "seats": [seat_id]}

    assert not service.matches_booking(booking, event_id, ["A1"], 100)
    booking["seats"] = [seat_id, seat_id]
    assert not service.matches_booking(booking, event_id, ["A1", "A2"], 100)


def test_booking_retry_returns_existing_booking_when_event_changed():
    event_id, user_id, seat_id = ObjectId(), ObjectId(), ObjectId()
    booking = {
        "eventId": event_id,
        "userId": user_id,
        "totalAmount": 100,
        "seats": [seat_id],
        "reservationId": "reservation-1",
    }
    events, bookings, seats = Mock(), Mock(), Mock()
    events.find_one.return_value = {"_id": event_id, "status": "archived", "price": 200}
    bookings.find_one.return_value = booking
    seats.find.return_value = [{"_id": seat_id, "seatNumber": "A1"}]
    service = BookingService({"events": events, "bookings": bookings, "seats": seats})

    result = service.create_booking(
        str(user_id), str(event_id), ["A1"], 100, "reservation-1"
    )

    assert result["replayed"] is True
    assert result["data"] == booking
    seats.update_many.assert_not_called()


def test_booking_retry_rejects_a_different_amount():
    event_id, user_id, seat_id = ObjectId(), ObjectId(), ObjectId()
    events, bookings, seats = Mock(), Mock(), Mock()
    events.find_one.return_value = {"_id": event_id, "price": 100}
    bookings.find_one.return_value = {
        "eventId": event_id,
        "totalAmount": 100,
        "seats": [seat_id],
    }
    seats.find.return_value = [{"_id": seat_id, "seatNumber": "A1"}]
    service = BookingService({"events": events, "bookings": bookings, "seats": seats})

    with pytest.raises(BookingError, match="different booking request"):
        service.create_booking(str(user_id), str(event_id), ["A1"], 200, "reservation-1")