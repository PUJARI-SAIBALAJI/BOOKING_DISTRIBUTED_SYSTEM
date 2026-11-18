import pytest

from backend.services.payment_service import (
    PaymentService,
    PaymentError
)


class FakeDatabase:

    def __getitem__(self, name):
        return object()


def create_service():
    return PaymentService(FakeDatabase())


def test_payment_methods():

    assert PaymentService.METHODS == [
        "UPI",
        "CARD",
        "NET_BANKING",
        "WALLET"
    ]


def test_payment_outcomes():

    assert PaymentService.OUTCOMES == [
        "success",
        "failed",
        "pending",
        "timeout"
    ]


def test_invalid_booking_id():

    service = create_service()

    with pytest.raises(PaymentError):
        service.validate_request(
            "invalid",
            100,
            "key-123",
            "UPI",
            "success"
        )


def test_negative_amount():

    service = create_service()

    with pytest.raises(PaymentError):
        service.validate_request(
            "507f1f77bcf86cd799439011",
            -100,
            "key-123",
            "UPI",
            "success"
        )


def test_invalid_method():

    service = create_service()

    with pytest.raises(PaymentError):
        service.validate_request(
            "507f1f77bcf86cd799439011",
            100,
            "key-123",
            "CASH",
            "success"
        )


def test_invalid_outcome():

    service = create_service()

    with pytest.raises(PaymentError):
        service.validate_request(
            "507f1f77bcf86cd799439011",
            100,
            "key-123",
            "UPI",
            "unknown"
        )


def test_empty_idempotency_key():

    service = create_service()

    with pytest.raises(PaymentError):
        service.validate_request(
            "507f1f77bcf86cd799439011",
            100,
            "",
            "UPI",
            "success"
        )


def test_idempotency_key_too_long():

    service = create_service()

    with pytest.raises(PaymentError):
        service.validate_request(
            "507f1f77bcf86cd799439011",
            100,
            "x" * 129,
            "UPI",
            "success"
        )


def test_valid_payment_request():

    service = create_service()

    result = service.validate_request(
        "507f1f77bcf86cd799439011",
        500,
        "payment-key-123",
        "UPI",
        "success"
    )

    assert result == "payment-key-123"


def test_all_payment_methods_are_accepted():

    service = create_service()

    for method in service.METHODS:

        result = service.validate_request(
            "507f1f77bcf86cd799439011",
            500,
            "key-" + method,
            method,
            "success"
        )

        assert result is not None


def test_all_payment_outcomes_are_accepted():

    service = create_service()

    for outcome in service.OUTCOMES:

        result = service.validate_request(
            "507f1f77bcf86cd799439011",
            500,
            "key-" + outcome,
            "UPI",
            outcome
        )

        assert result is not None