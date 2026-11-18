from datetime import datetime, timedelta, timezone

import pytest

from bson import ObjectId
from unittest.mock import MagicMock, patch

from backend.services.seat_reservation_service import (
    SeatReservationService,
    ReservationError
)


@pytest.fixture
def service():

    return SeatReservationService(MagicMock())


def test_valid_request(service):

    event_id = str(ObjectId())
    user_id = str(ObjectId())

    result = service.validate_request(
        event_id,
        ["A1", "A2"],
        user_id
    )

    assert result == ["A1", "A2"]


def test_invalid_event_id(service):

    with pytest.raises(ReservationError):

        service.validate_request(
            "invalid",
            ["A1"],
            str(ObjectId())
        )


def test_invalid_user_id(service):

    with pytest.raises(ReservationError):

        service.validate_request(
            str(ObjectId()),
            ["A1"],
            "invalid"
        )


def test_empty_seat_selection(service):

    with pytest.raises(ReservationError):

        service.validate_request(
            str(ObjectId()),
            [],
            str(ObjectId())
        )


def test_more_than_20_seats(service):

    seats = [
        f"A{i}"
        for i in range(1, 22)
    ]

    with pytest.raises(ReservationError):

        service.validate_request(
            str(ObjectId()),
            seats,
            str(ObjectId())
        )


def test_duplicate_seats(service):

    with pytest.raises(ReservationError):

        service.validate_request(
            str(ObjectId()),
            ["A1", "A1"],
            str(ObjectId())
        )


def test_empty_seat_number(service):

    with pytest.raises(ReservationError):

        service.validate_request(
            str(ObjectId()),
            ["A1", " "],
            str(ObjectId())
        )


def test_lock_duration():

    assert SeatReservationService.LOCK_DURATION_MS == 300000


def test_expiry_time():

    now = datetime.now(timezone.utc)

    expires = now + timedelta(
        milliseconds=SeatReservationService.LOCK_DURATION_MS
    )

    assert expires > now