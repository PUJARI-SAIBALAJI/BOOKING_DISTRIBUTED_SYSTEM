from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest

from frontend.utils.api import _normalize_booking
from frontend.utils.booking_time import format_booking_timestamp
from frontend.components import booking_card
from frontend.pages import admin_bookings, confirmation


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        ("2026-11-17T20:52:35.713Z", "2026-11-18 02:22:35 IST"),
        ("2026-11-17T20:52:35.713", "2026-11-18 02:22:35 IST"),
        ("2026-11-18T02:22:35+05:30", "2026-11-18 02:22:35 IST"),
        (datetime(2026, 11, 17, 15, 52, 35, tzinfo=timezone(-timedelta(hours=5))),
         "2026-11-18 02:22:35 IST"),
        (None, "Unavailable"),
        ("", "Unavailable"),
        ("not-a-date", "Invalid timestamp"),
    ],
)
def test_booking_timestamp_display(value, expected):
    assert format_booking_timestamp(value) == expected


def test_normalized_booking_shows_ist_without_changing_original_timestamp():
    raw = {"_id": "test", "createdAt": "2026-11-17T20:52:35Z"}
    result = _normalize_booking(raw)
    assert result["booked_on"] == "2026-11-18 02:22:35 IST"
    assert result["createdAt"] == raw["createdAt"]


def test_admin_booking_table_shows_ist():
    booking = {
        "_id": "test",
        "createdAt": "2026-11-17T20:52:35Z",
        "updatedAt": "2026-11-17T21:00:00",
    }
    with patch.object(admin_bookings, "st") as streamlit:
        streamlit.session_state.auth_token = "test-token"
        streamlit.columns.return_value = (streamlit, streamlit)
        with patch.object(admin_bookings, "get_admin_bookings", return_value=[booking]):
            with patch.object(admin_bookings, "render_admin_nav"), \
                    patch.object(admin_bookings, "page_header"), \
                    patch.object(admin_bookings, "breadcrumb"), \
                    patch.object(admin_bookings, "render_poster"):
                admin_bookings.render()
        row = streamlit.dataframe.call_args.args[0][0]
    assert row["Created At (IST)"] == "2026-11-18 02:22:35 IST"
    assert row["Updated At (IST)"] == "2026-11-18 02:30:00 IST"


def test_booking_card_shows_formatted_timestamp():
    booking = {
        "id": "test", "status": "Pending", "seats": ["A1"],
        "booked_on": "2026-11-18 02:22:35 IST",
    }
    with patch.object(booking_card, "st") as streamlit:
        streamlit.columns.side_effect = [(streamlit, streamlit), (streamlit, streamlit, streamlit)]
        with patch.object(booking_card, "event_for_booking", return_value={"title": "Test"}), \
                patch.object(booking_card, "render_poster"):
            booking_card.render_booking_card(booking)
        assert any(
            "Booked: 2026-11-18 02:22:35 IST" in call.args[0]
            for call in streamlit.markdown.call_args_list
        )


def test_confirmation_shows_formatted_timestamp():
    booking = {
        "id": "test", "seats": ["A1"], "amount": 1,
        "booked_on": "2026-11-18 02:22:35 IST",
    }
    with patch.object(confirmation, "st") as streamlit:
        streamlit.session_state.booking = booking
        streamlit.columns.side_effect = [(streamlit, streamlit), (streamlit, streamlit, streamlit)]
        streamlit.button.return_value = False
        with patch.object(confirmation, "page_header"), \
                patch.object(confirmation, "breadcrumb"), \
                patch.object(confirmation, "render_poster"):
            confirmation.render()
        assert any(
            "Booked: 2026-11-18 02:22:35 IST" in call.args[0]
            for call in streamlit.markdown.call_args_list
        )
