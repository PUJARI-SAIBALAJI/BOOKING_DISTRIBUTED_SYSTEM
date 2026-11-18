from backend.database.mongodb import initialize_application_indexes


class RecordingCollection:
    def __init__(self):
        self.indexes = []

    def create_index(self, keys, **options):
        self.indexes.append((keys, options))


class RecordingDatabase:
    def __init__(self):
        self.collections = {}

    def __getitem__(self, name):
        return self.collections.setdefault(name, RecordingCollection())


def test_application_indexes_match_existing_legacy_index_definitions():
    database = RecordingDatabase()

    initialize_application_indexes(database)

    assert database["users"].indexes == [
        ("email", {"unique": True}),
    ]
    assert database["seats"].indexes == [
        ([("eventId", 1), ("seatNumber", 1)], {"unique": True}),
    ]
    assert database["bookings"].indexes == [
        (
            [("userId", 1), ("reservationId", 1)],
            {
                "unique": True,
                "partialFilterExpression": {
                    "reservationId": {"$type": "string"},
                },
            },
        ),
    ]
    assert database["payments"].indexes == [
        (
            "idempotencyKey",
            {
                "unique": True,
                "partialFilterExpression": {
                    "idempotencyKey": {"$type": "string"},
                },
            },
        ),
    ]
    assert database["refunds"].indexes == [
        ("idempotencyKey", {"unique": True}),
        ("bookingId", {"unique": True}),
    ]
