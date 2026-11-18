import pytest

from unittest.mock import MagicMock, patch

from bson import ObjectId

from backend.services.event_service import (
    EventService,
    EventError
)


@pytest.fixture
def service():

    return EventService(MagicMock())


def test_row_label():

    assert EventService.row_label(0) == "A"
    assert EventService.row_label(25) == "Z"
    assert EventService.row_label(26) == "AA"
    assert EventService.row_label(27) == "AB"


def test_seat_numbers_generation():

    result = EventService.seat_numbers_to_add(
        5,
        3
    )

    assert result == [
        "A1",
        "A2",
        "A3",
        "B1",
        "B2"
    ]


def test_seat_numbers_skip_existing():

    result = EventService.seat_numbers_to_add(
        4,
        3,
        ["A1", "A2"]
    )

    assert result == [
        "A3",
        "B1"
    ]


def test_seat_category():

    assert EventService.seat_category(0, 100) == "VIP"
    assert EventService.seat_category(25, 100) == "Platinum"
    assert EventService.seat_category(50, 100) == "Gold"
    assert EventService.seat_category(75, 100) == "Silver"


def test_seat_index():

    assert EventService.seat_index("A1", 10) == 0
    assert EventService.seat_index("A5", 10) == 4
    assert EventService.seat_index("B1", 10) == 10
    assert EventService.seat_index("AA1", 10) == 260


def test_invalid_event_id(service):

    with pytest.raises(EventError):

        service.get_event("invalid-id")


def test_invalid_delete_id(service):

    with pytest.raises(EventError):

        service.delete_event("invalid-id")


def test_invalid_update_id(service):

    with pytest.raises(EventError):

        service.update_event("invalid-id", {})


def test_invalid_create_event(service):

    with pytest.raises(EventError):

        service.create_event({})


def test_seat_generation_document_count(service):

    with patch(
        "backend.services.event_service.Seat.collection"
    ) as mock_collection:

        mock_collection.return_value.insert_many = MagicMock()

        event_id = ObjectId()

        count = service.generate_seats(
            event_id,
            5,
            3
        )

        assert count == 5

        inserted = (
            mock_collection.return_value.insert_many
            .call_args[0][0]
        )

        assert len(inserted) == 5
        assert inserted[0]["seatNumber"] == "A1"
        assert inserted[0]["category"] == "VIP"