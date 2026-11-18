from datetime import datetime, timedelta, timezone
from unittest.mock import Mock

from bson import ObjectId

from backend.raft.state_machine import RaftStateMachine
from backend.services.seat_reservation_service import SeatReservationService


def test_raft_reservation_uses_committed_operation_time():
    database = {
        name: Mock()
        for name in ("raftcommandresults", "bookings", "seats", "payments", "refunds")
    }
    machine = RaftStateMachine(database)
    machine.reservation_service = Mock()
    payload = {
        "event_id": "event",
        "user_id": "user",
        "seat_numbers": ["A1"],
        "reservation_id": "reservation",
        "_raftTimestamp": "2026-11-18T02:00:00+00:00",
    }

    machine.execute_business_command("RESERVE_SEATS", payload, "command-1")

    assert machine.reservation_service.reserve_seats.call_args.kwargs["operation_time"] == datetime(
        2026, 11, 18, 2, 0, tzinfo=timezone.utc
    )


def test_reservation_replay_uses_log_time_with_naive_mongo_date():
    event_id, user_id = ObjectId(), ObjectId()
    now = datetime(2026, 11, 18, 2, 0, tzinfo=timezone.utc)
    seat = {
        "seatNumber": "A1",
        "status": "reserved",
        "bookingId": None,
        "reservationId": "reservation",
        "reservedBy": user_id,
        "lockExpiresAt": (now + timedelta(minutes=5)).replace(tzinfo=None),
    }
    seats = Mock()
    cursor = Mock()
    cursor.sort.return_value = [seat]
    seats.find.side_effect = [[seat], cursor]
    seats.find_one_and_update.return_value = seat
    bookings = Mock()
    bookings.find_one.return_value = None
    service = SeatReservationService({"seats": seats, "bookings": bookings})

    result = service.reserve_seats(
        str(event_id), ["A1"], str(user_id), "reservation", operation_time=now
    )

    assert result["expiresAt"] == now + timedelta(minutes=5)
    assert seats.find.call_args.args[0]["lockExpiresAt"] == {"$gt": now}
