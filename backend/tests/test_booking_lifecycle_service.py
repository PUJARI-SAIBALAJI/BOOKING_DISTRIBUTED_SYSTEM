from datetime import datetime, timedelta, timezone

import pytest

from backend.services.booking_lifecycle_service import (
    BookingLifecycleService,
    BookingLifecycleError
)


class FakeCursor(list):

    def sort(self, *args, **kwargs):
        return self

    def limit(self, count):
        return FakeCursor(self[:count])


class FakeCollection:

    def __init__(self, documents=None):
        self.documents = documents or []

    def find(self, query):
        return FakeCursor()

    def find_one(self, query):
        return None

    def find_one_and_update(self, query, update, return_document=None):
        return None

    def update_many(self, query, update):
        return None


class FakeDatabase:

    def __getitem__(self, name):
        return FakeCollection()


def create_service():
    return BookingLifecycleService(FakeDatabase())


def test_service_initialization():
    service = create_service()

    assert service.bookings is not None
    assert service.seats is not None
    assert service.payments is not None


def test_invalid_user_id_for_listing():
    service = create_service()

    with pytest.raises(BookingLifecycleError):
        service.get_user_bookings("invalid-id")


def test_invalid_booking_id():
    service = create_service()

    with pytest.raises(BookingLifecycleError):
        service.get_booking("invalid-id", "507f1f77bcf86cd799439011")


def test_invalid_user_id_for_booking():
    service = create_service()

    with pytest.raises(BookingLifecycleError):
        service.get_booking("507f1f77bcf86cd799439011", "invalid-id")


def test_invalid_reference():
    service = create_service()

    with pytest.raises(BookingLifecycleError):
        service.get_booking_by_reference(
            "",
            "507f1f77bcf86cd799439011"
        )


def test_invalid_user_for_reference():
    service = create_service()

    with pytest.raises(BookingLifecycleError):
        service.get_booking_by_reference(
            "FR-123456",
            "invalid-id"
        )


def test_invalid_booking_for_cancellation():
    service = create_service()

    with pytest.raises(BookingLifecycleError):
        service.cancel_booking(
            "invalid-id",
            "507f1f77bcf86cd799439011"
        )


def test_invalid_user_for_cancellation():
    service = create_service()

    with pytest.raises(BookingLifecycleError):
        service.cancel_booking(
            "507f1f77bcf86cd799439011",
            "invalid-id"
        )


def test_cleanup_returns_counts():
    service = create_service()

    result = service.cleanup_expired_bookings()

    assert result == {
        "expiredBookings": 0,
        "cleanedTerminalBookings": 0
    }


def test_cleanup_accepts_specific_time():
    service = create_service()

    now = datetime.now(timezone.utc)

    result = service.cleanup_expired_bookings(now=now)

    assert "expiredBookings" in result
    assert "cleanedTerminalBookings" in result


def test_cleanup_rejects_invalid_event_id():
    service = create_service()

    with pytest.raises(BookingLifecycleError):
        service.cleanup_expired_bookings(
            event_id="invalid-event-id"
        )