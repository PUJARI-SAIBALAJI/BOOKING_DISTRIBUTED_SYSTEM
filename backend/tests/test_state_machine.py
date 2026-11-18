import pytest

from unittest.mock import MagicMock

from backend.raft.state_machine import (
    RaftStateMachine,
    StateMachineError
)

from backend.services.booking_service import BookingError


@pytest.fixture
def state_machine():

    machine = RaftStateMachine.__new__(RaftStateMachine)

    machine.commands = MagicMock()
    machine.commands.update_one.return_value.modified_count = 1

    machine.local_lock = __import__("threading").RLock()

    machine.booking_service = MagicMock()
    machine.lifecycle_service = MagicMock()
    machine.payment_service = MagicMock()
    machine.refund_service = MagicMock()

    return machine


# --------------------------------------------------
# 1. SUCCESSFUL COMMAND EXECUTION
# --------------------------------------------------

def test_successful_command_execution(state_machine):

    payload = {
        "user_id": "user123",
        "event_id": "event123",
        "seat_numbers": ["A1"],
        "total_amount": 500,
        "reservation_id": "reservation123"
    }

    state_machine.commands.find_one.return_value = {
        "commandId": "cmd-001",
        "commandType": "CREATE_BOOKING",
        "payload": payload,
        "status": "pending"
    }

    state_machine.commands.find_one_and_update.return_value = {
        "commandId": "cmd-001",
        "status": "processing"
    }

    expected_result = {
        "booking_id": "booking123"
    }

    state_machine.booking_service.create_booking.return_value = (
        expected_result
    )

    result = state_machine.apply_command(
        "cmd-001",
        "CREATE_BOOKING",
        payload
    )

    assert result["success"] is True
    assert result["replayed"] is False

    state_machine.booking_service.create_booking.assert_called_once()

    state_machine.commands.update_one.assert_called()


# --------------------------------------------------
# 2. DUPLICATE COMMAND REPLAY
# --------------------------------------------------

def test_completed_command_is_not_executed_again(state_machine):

    payload = {
        "booking_id": "booking123",
        "user_id": "user123"
    }

    saved_result = {
        "booking_id": "booking123",
        "status": "confirmed"
    }

    state_machine.commands.find_one.return_value = {
        "commandId": "cmd-002",
        "commandType": "CANCEL_BOOKING",
        "payload": payload,
        "status": "completed",
        "result": saved_result
    }

    result = state_machine.apply_command(
        "cmd-002",
        "CANCEL_BOOKING",
        payload
    )

    assert result["success"] is True
    assert result["replayed"] is True
    assert result["result"] == saved_result

    state_machine.lifecycle_service.cancel_booking.assert_not_called()


# --------------------------------------------------
# 3. INVALID COMMAND
# --------------------------------------------------

def test_invalid_command_is_rejected(state_machine):

    payload = {}

    state_machine.commands.find_one.return_value = {
        "commandId": "cmd-003",
        "commandType": "INVALID_COMMAND",
        "payload": payload,
        "status": "pending"
    }

    state_machine.commands.find_one_and_update.return_value = {
        "commandId": "cmd-003",
        "status": "processing"
    }

    result = state_machine.apply_command(
        "cmd-003",
        "INVALID_COMMAND",
        payload
    )

    assert result["success"] is False
    assert "Unsupported command" in result["error"]

    state_machine.commands.update_one.assert_called()


# --------------------------------------------------
# 4. BUSINESS SERVICE ERROR
# --------------------------------------------------

def test_booking_error_is_handled(state_machine):

    payload = {
        "user_id": "invalid",
        "event_id": "invalid",
        "seat_numbers": ["A1"],
        "total_amount": 500,
        "reservation_id": "reservation123"
    }

    state_machine.commands.find_one.return_value = {
        "commandId": "cmd-004",
        "commandType": "CREATE_BOOKING",
        "payload": payload,
        "status": "pending"
    }

    state_machine.commands.find_one_and_update.return_value = {
        "commandId": "cmd-004",
        "status": "processing"
    }

    state_machine.booking_service.create_booking.side_effect = (
        BookingError("Invalid user ID", 400)
    )

    result = state_machine.apply_command(
        "cmd-004",
        "CREATE_BOOKING",
        payload
    )

    assert result["success"] is False
    assert result["error"] == "Invalid user ID"
    assert result["status_code"] == 400
    state_machine.commands.update_one.assert_called()


def test_failed_command_replay_preserves_failure(state_machine):
    payload = {"booking_id": "booking123"}
    failure = {
        "error": "Seat is unavailable",
        "status_code": 409,
    }
    state_machine.commands.find_one.return_value = {
        "commandId": "cmd-failed",
        "commandType": "CREATE_BOOKING",
        "payload": payload,
        "status": "failed",
        "result": failure,
    }

    result = state_machine.apply_command(
        "cmd-failed",
        "CREATE_BOOKING",
        payload,
    )

    assert result == {
        "success": False,
        "replayed": True,
        "result": failure,
    }
    state_machine.booking_service.create_booking.assert_not_called()


# --------------------------------------------------
# 5. COMMAND ALREADY BEING PROCESSED
# --------------------------------------------------

def test_processing_command_is_not_executed_twice(state_machine):

    payload = {
        "booking_id": "booking123",
        "user_id": "user123"
    }

    state_machine.commands.find_one.return_value = {
        "commandId": "cmd-005",
        "commandType": "CANCEL_BOOKING",
        "payload": payload,
        "status": "processing"
    }

    # Another worker currently owns the processing lease.
    state_machine.commands.find_one_and_update.return_value = None

    result = state_machine.apply_command(
        "cmd-005",
        "CANCEL_BOOKING",
        payload
    )

    assert result["success"] is False
    assert result["pending"] is True

    state_machine.lifecycle_service.cancel_booking.assert_not_called()


# --------------------------------------------------
# 6. JSON PAYLOAD NORMALIZATION
# --------------------------------------------------

def test_json_payload_is_normalized(state_machine):

    payload = '{"booking_id": "booking123"}'

    result = state_machine.normalize_payload(payload)

    assert isinstance(result, dict)
    assert result["booking_id"] == "booking123"


# --------------------------------------------------
# 7. INVALID PAYLOAD
# --------------------------------------------------

def test_invalid_payload_is_rejected(state_machine):

    with pytest.raises(StateMachineError):

        state_machine.normalize_payload(
            "this is not valid JSON"
        )


# --------------------------------------------------
# 8. MISSING COMMAND ID
# --------------------------------------------------

def test_missing_command_id_is_rejected(state_machine):

    with pytest.raises(StateMachineError):

        state_machine.apply_command(
            "",
            "CANCEL_BOOKING",
            {}
        )


# --------------------------------------------------
# 9. PAYMENT COMMAND DISPATCH
# --------------------------------------------------

def test_payment_command_dispatch(state_machine):

    payload = {
        "booking_id": "booking123",
        "user_id": "user123",
        "amount": 500,
        "idempotency_key": "payment-key-1",
        "method": "UPI",
        "outcome": "success"
    }

    expected = {"payment": "successful"}

    state_machine.payment_service.process_mock_payment.return_value = (
        expected
    )

    result = state_machine.execute_business_command(
        "PROCESS_PAYMENT",
        payload
    )

    assert result == expected

    state_machine.payment_service.process_mock_payment.assert_called_once_with(
        booking_id="booking123",
        user_id="user123",
        amount=500,
        idempotency_key="payment-key-1",
        method="UPI",
        outcome="success"
    )


# --------------------------------------------------
# 10. REFUND COMMAND DISPATCH
# --------------------------------------------------

def test_refund_command_dispatch(state_machine):

    payload = {
        "booking_id": "booking123",
        "user_id": "user123",
        "idempotency_key": "refund-key-1",
        "outcome": "success"
    }

    expected = {"refund": "successful"}

    state_machine.refund_service.create_refund.return_value = (
        expected
    )

    result = state_machine.execute_business_command(
        "PROCESS_REFUND",
        payload
    )

    assert result == expected

    state_machine.refund_service.create_refund.assert_called_once_with(
        booking_id="booking123",
        user_id="user123",
        idempotency_key="refund-key-1",
        outcome="success"
    )