import pytest
from bson import ObjectId

from backend.models.refund import Refund


def valid_refund():
    return {
        "bookingId": str(ObjectId()),
        "userId": str(ObjectId()),
        "amount": 1500,
        "idempotencyKey": "refund-key-001",
        "transactionId": "refund-txn-001",
    }


def test_valid_refund():
    refund = Refund.validate(valid_refund())

    assert refund["amount"] == 1500
    assert refund["status"] == "processing"


def test_default_status():
    refund = Refund.validate(valid_refund())

    assert refund["status"] == "processing"


def test_invalid_booking_id():
    data = valid_refund()
    data["bookingId"] = "invalid-id"

    with pytest.raises(ValueError):
        Refund.validate(data)


def test_invalid_user_id():
    data = valid_refund()
    data["userId"] = "invalid-id"

    with pytest.raises(ValueError):
        Refund.validate(data)


def test_negative_amount():
    data = valid_refund()
    data["amount"] = -100

    with pytest.raises(ValueError):
        Refund.validate(data)


def test_invalid_status():
    data = valid_refund()
    data["status"] = "pending"

    with pytest.raises(ValueError):
        Refund.validate(data)


def test_empty_idempotency_key():
    data = valid_refund()
    data["idempotencyKey"] = "   "

    with pytest.raises(ValueError):
        Refund.validate(data)


def test_empty_transaction_id():
    data = valid_refund()
    data["transactionId"] = "   "

    with pytest.raises(ValueError):
        Refund.validate(data)


def test_prepare_adds_timestamps():
    refund = Refund.prepare(valid_refund())

    assert "createdAt" in refund
    assert "updatedAt" in refund


def test_refund_status_values():
    assert Refund.STATUSES == {
        "processing",
        "success",
        "failed",
    }