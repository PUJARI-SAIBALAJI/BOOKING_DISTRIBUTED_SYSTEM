import pytest

from bson import ObjectId

from backend.models.payment import Payment


def sample_payment():

    return {

        "bookingId": ObjectId(),

        "userId": ObjectId(),

        "amount": 3000,

        "transactionId": "TXN-12345",

        "idempotencyKey": "IDEMP-12345",

        "method": "UPI",

        "mockOutcome": "success",

        "status": "processing"
    }


def test_valid_payment():

    assert Payment.validate(sample_payment()) is True


def test_missing_booking_id():

    data = sample_payment()

    del data["bookingId"]

    with pytest.raises(ValueError):

        Payment.validate(data)


def test_missing_user_id():

    data = sample_payment()

    del data["userId"]

    with pytest.raises(ValueError):

        Payment.validate(data)


def test_negative_amount():

    data = sample_payment()

    data["amount"] = -100

    with pytest.raises(ValueError):

        Payment.validate(data)


def test_invalid_payment_method():

    data = sample_payment()

    data["method"] = "CASH"

    with pytest.raises(ValueError):

        Payment.validate(data)


def test_invalid_mock_outcome():

    data = sample_payment()

    data["mockOutcome"] = "completed"

    with pytest.raises(ValueError):

        Payment.validate(data)


def test_invalid_payment_status():

    data = sample_payment()

    data["status"] = "cancelled"

    with pytest.raises(ValueError):

        Payment.validate(data)


def test_default_payment_status():

    data = sample_payment()

    del data["status"]

    document = Payment.prepare(data)

    assert document["status"] == "processing"


def test_object_id_conversion():

    data = sample_payment()

    data["bookingId"] = str(data["bookingId"])

    document = Payment.prepare(data)

    assert isinstance(
        document["bookingId"],
        ObjectId
    )


def test_transaction_id_trimming():

    data = sample_payment()

    data["transactionId"] = " TXN-12345 "

    document = Payment.prepare(data)

    assert document["transactionId"] == "TXN-12345"