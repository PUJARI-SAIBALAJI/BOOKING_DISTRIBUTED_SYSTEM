# FlashReserve

FlashReserve uses a Streamlit frontend and a Python REST backend. MongoDB is
required. The REST API serves standalone **Normal Mode** and exposes a Raft
gateway under `/api/raft`. Raft-mode writes are submitted to the current leader
and return only after majority commitment and leader state-machine application.
Raft node processes expose gRPC consensus; the frontend does not call their
gRPC ports directly.

Event catalogues are mode-specific: Normal Mode reads and writes events in
the standalone database; Raft Mode reads and writes events through the Raft
leader and does not import the standalone catalogue. Create or maintain an
event in each mode where it should be available. The account store used for
login and the notification outbox are still shared in the standalone database,
so the two modes are not fully database-independent for identity and email
delivery.

## Windows development

For individual Git Bash commands and current startup limitations, see the
[startup guide](STARTUP_GUIDE.md).

For manual setup, create and activate a virtual environment, then install the
project dependencies:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Alternatively, run:

```bat
setup.bat
```

The setup script does not overwrite an existing `.env`; if none exists, it
copies `.env.example` with placeholders. Replace placeholders before starting
services. `.env` is listed in `.gitignore`. Configure `MONGODB_URI` (or the
legacy `STANDALONE_MONGO_URI`), `STANDALONE_DB_NAME` (or legacy
`DATABASE_NAME`), and a private `JWT_SECRET`. `PORT` takes precedence over the
legacy `APP_PORT`. `API_BASE_URL` sets the normal-mode frontend API URL, with
`FLASHRESERVE_NORMAL_API_URL` retained for compatibility. Booking and payment
code uses MongoDB transactions, so the MongoDB deployment must support
transactions.

Start the REST API and Streamlit frontend in separate terminals:

```bat
start_backend.bat
```

```bat
start_frontend.bat
```

The standalone API health endpoint is `http://127.0.0.1:5000/api/health` with
the default configuration.

## LLM support service

The LLM gRPC service listens on `LLM_GRPC_HOST`/`LLM_GRPC_PORT` (defaults:
`127.0.0.1:50060`). Configure `GROQ_API_KEY` and `GROQ_MODEL` for provider
responses. If the provider is not configured or is unavailable, the service
returns a labeled FAQ fallback.

```bat
.venv\Scripts\python.exe -m llm.llm_service
```

## Raft nodes

Each Raft process requires its own `RAFT_NODE_<n>_MONGO_URI`; it never falls
back to the standalone Mongo URI. Configure independent endpoints, node
addresses, ports, and the same odd `RAFT_CLUSTER_SIZE` on every process.

Each Raft node selects its own configured database with
`RAFT_NODE_<n>_DATABASE_NAME`. All seven nodes may use the same Atlas URI; the
database names must be distinct. The configured names in `.env.example`
reflect the existing `flashreserve_raft_node1` through
`flashreserve_raft_node7` databases. Separate databases provide persistence
isolation, not replication: log entries and committed commands are propagated
through Raft gRPC.

Raft MongoDB server selection is bounded by
`RAFT_MONGO_SERVER_SELECTION_TIMEOUT_MS` (default 1000 ms, and it must be
shorter than `RAFT_RPC_TIMEOUT`). This keeps a disconnected database from
holding a node's Raft lock longer than peer RPC deadlines. The node still
requires its MongoDB database to be reachable to persist terms, votes, and
logs; failed persistence prevents elections and writes rather than weakening
Raft durability.

For a local development cluster only, `start_all_raft_nodes.bat` checks that
the seven Raft Mongo URIs are configured, node addresses resolve to this
machine, and RPC ports are unique and free, then launches seven separate
processes. `stop_raft_nodes.bat` stops only those recorded processes after
checking their executable and command line.

For nodes on separate machines, configure each machine with its own node ID,
RPC address, and independent `RAFT_NODE_<n>_MONGO_URI`, then run on that
machine:

```bat
start_raft_node.bat node-1
```

Replace `node-1` with that machine's configured node ID. Stop an individually
started node with `Ctrl+C`. These commands start gRPC Raft processes. The frontend communicates with the
REST gateway at `RAFT_API_BASE_URL` (defaults to `API_BASE_URL`); it must not
send HTTP requests to the node gRPC ports. Authentication uses the existing
standalone account store, while Raft events, reservations, bookings, payments,
and cancellations are stored in the Raft node databases. Raft event reads do
not copy the standalone event catalogue. The account store is read for identity
and authorization; credentials and email addresses are not copied into Raft
log entries. The standalone notification outbox remains shared by both modes.
The sign-in / create-account screen displays live status for all Raft nodes,
including leader, quorum, database, and log information. The monitor is
available only before sign-in and is not shown on authenticated pages. Its
compact table includes per-follower replication acknowledgements
(ACKNOWLEDGED, PENDING, FAILED, CATCHING UP, or UNREACHABLE); detailed log,
commit, application, and recovery data remains available in node details.

This implementation has no snapshot installation, and its mock payment and
SMTP notification behavior are not a production payment/mail system. Do not
deploy it as a production ticketing system until the listed recovery and
failure-injection tests have been run against an isolated cluster.

## Booking emails

The backend creates the poster upload directory at startup. Booking
confirmation emails are queued after a successful mock payment confirms the
booking; cancellation emails are queued after cancellation. In Raft Mode the
gateway queues them only after the operation is committed and applied. The
destination is the signed-in account's email address, not `SMTP_USER`.

Configure `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD`, and
`SMTP_FROM_NAME` in `.env`, then restart the backend. The backend worker sends
queued messages using SMTP STARTTLS. The `notificationoutbox` collection is in
the standalone database for both modes; it holds delivery metadata and email
details, not Raft booking state. Queue entries are deduplicated by mode,
booking ID, and notification type. Known failures are logged and retried.
An interrupted or ambiguous sending attempt is marked `delivery_unknown`
instead of being automatically resent, since SMTP cannot guarantee exactly-once
delivery. SMTP acceptance does not prove delivery to an inbox.

The queue insertion follows the booking operation rather than sharing its
transaction. If the backend stops between the booking operation and queue
insertion, no email is queued until the same operation is retried. A queue
failure returns an error explaining that the booking operation completed.
Existing bookings are not automatically backfilled with notifications. This
workflow is not atomic across the booking and notification queue.

A uniquely labelled Normal Mode test using the real Atlas database and the
in-process REST application created, paid for, and cancelled a test booking.
SMTP accepted both test messages; inbox delivery was not verified. The test
event was archived and its test records were retained. Raft booking email
delivery has not been live-tested.

Booking creation and update timestamps are displayed in India Standard Time
(`Asia/Kolkata`) in the application. MongoDB continues to store BSON dates in
UTC; Compass may therefore show UTC timestamps. Event dates and times remain
as entered by the event administrator.

## Tests

The tests use fakes for MongoDB and do not write to a configured database, send
email, or make paid provider requests:

```bat
run_tests.bat
```

See the [architecture audit](docs/architecture-audit.md), [migration recovery
report](docs/migration-recovery-report.md), and
[implementation report](docs/implementation-report.md) for verified scope and
remaining work.
