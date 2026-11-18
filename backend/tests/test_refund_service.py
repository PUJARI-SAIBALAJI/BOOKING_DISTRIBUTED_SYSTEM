import pytest

from backend.services.refund_service import (
    RefundService,
    RefundError
)


class FakeDatabase:

    def __getitem__(self, name):
        return object()


def create_service():
    return RefundService(FakeDatabase())


def test_refund_statuses():

    assert RefundService.STATUSES == [
        "processing",
        "success",
        "failed"
    ]


def test_invalid_booking_id():

    service = create_service()

    with pytest.raises(RefundError):
        service.validate_request("invalid", "refund-123")


def test_empty_idempotency_key():

    service = create_service()

    with pytest.raises(RefundError):
        service.validate_request(
            "507f1f77bcf86cd799439011",
            ""
        )


def test_long_idempotency_key():

    service = create_service()

    with pytest.raises(RefundError):
        service.validate_request(
            "507f1f77bcf86cd799439011",
            "x" * 129
        )


def test_valid_idempotency_key():

    service = create_service()

    result = service.validate_request(
        "507f1f77bcf86cd799439011",
        "refund-key-123"
    )

    assert result == "refund-key-123"


def test_invalid_refund_outcome():

    service = create_service()

    with pytest.raises(RefundError):
        service.create_refund(
            "507f1f77bcf86cd799439011",
            "507f1f77bcf86cd799439012",
            "refund-key",
            outcome="pending"
        )


def test_invalid_user_id():

    service = create_service()

    with pytest.raises(RefundError):
        service.create_refund(
            "507f1f77bcf86cd799439011",
            "invalid-user",
            "refund-key"
        )


def test_invalid_refund_id():

    service = create_service()

    with pytest.raises(RefundError):
        service.get_refund(
            "invalid-refund",
            "507f1f77bcf86cd799439012"
        )


def test_invalid_user_for_refund():

    service = create_service()

    with pytest.raises(RefundError):
        service.get_refund(
            "507f1f77bcf86cd799439011",
            "invalid-user"
        )


def test_invalid_booking_for_refund_lookup():

    service = create_service()

    with pytest.raises(RefundError):
        service.get_booking_refund(
            "invalid-booking",
            "507f1f77bcf86cd799439012"
        )