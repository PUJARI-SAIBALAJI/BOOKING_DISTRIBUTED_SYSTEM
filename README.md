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


---

# FlashReserve – Distributed Ticket Booking System
A distributed ticket booking platform built using **Python, Streamlit, FastAPI/REST, gRPC, MongoDB, Raft Consensus Algorithm, and LLM integration**.

FlashReserve provides real-time event discovery, seat selection, concurrent booking, mock payment processing, booking management, email notifications, and a distributed booking architecture with seven Raft nodes.

The application supports two operating modes:

1. **Normal Mode** – Uses a standalone MongoDB database and the REST backend.
2. **Raft Mode** – Uses a seven-node distributed cluster to replicate booking operations through the Raft Consensus Algorithm.

---

# 1. Project Overview
FlashReserve addresses the challenges of concurrent ticket reservations and distributed consistency.

For example, when multiple users attempt to reserve the same seat simultaneously, the system must prevent duplicate bookings and overbooking.

The application provides:

- Real-time event and seat availability.
- Interactive seat selection.
- Concurrent booking management.
- Overbooking prevention.
- Mock payment processing.
- Booking confirmation and cancellation.
- Email notifications for successful bookings and cancellations.
- LLM-powered customer support chatbot.
- Seven-node Raft consensus cluster.
- Leader election and follower management.
- Log replication and majority commitment.
- Fault detection and recovery.
- Live Raft cluster monitoring.

# 2. Technology Stack
ComponentTechnologyFrontendStreamlit, PythonBackendPython REST APIDistributed CommunicationgRPCConsensus AlgorithmRaftDatabaseMongoDB AtlasDatabase DriverPyMongoLLM IntegrationGroq APILLM CommunicationgRPCEmail ServiceSMTP with STARTTLSTestingPytestVersion ControlGit and GitHub
# 3. System Architecture
FlashReserve follows a layered architecture.

## 3.1 High-Level Architecture

```
                  USERS
                    |
                    v
          STREAMLIT FRONTEND
              (Port 8502)
                    |
             Operating Mode
              /          \
             /            \
            v              v
       NORMAL MODE       RAFT MODE
            |                |
            v                v
       REST BACKEND      RAFT REST GATEWAY
       (Port 5000)       (/api/raft)
            |                |
            v                v
      STANDALONE DB      RAFT LEADER
      flashreserve            |
                              |
                     gRPC Communication
                              |
             +------------------------------+
             |              |               |
             v              v               v
           Node 1         Node 2          Node 3
             |              |               |
             +--------------+---------------+
                            |
                   Remaining Raft Nodes
                            |
                   +--------+--------+
                   |        |        |
                   v        v        v
                 Node 4   Node 5   Node 6
                            |
                           Node 7

                    MongoDB Databases
                            |
                     LLM gRPC Service
                            |
                        Groq API

                 SMTP Email Notification
```
**Important:** The frontend communicates with the REST backend and Raft gateway. It does not communicate directly with the individual Raft nodes' gRPC ports.

## 3.2 Operating Modes

### Normal Mode
Normal Mode uses the standalone MongoDB database.

Database:

`flashreserve`

Workflow:

1. User signs in.
2. User selects an event.
3. User selects available seats.
4. Frontend sends a booking request to the REST backend.
5. Backend validates seat availability.
6. MongoDB transaction handles the booking and payment workflow.
7. Booking confirmation is returned.
8. Email notification is queued.

### Raft Mode
Raft Mode uses the distributed Raft cluster.

Workflow:

1. User selects Raft Mode.
2. User selects an event and seats.
3. Frontend sends the booking request to the Raft REST gateway.
4. Gateway forwards the request to the current Raft leader.
5. Leader appends the operation to its log.
6. Leader replicates the log entry to followers through gRPC.
7. Followers acknowledge successful replication.
8. Leader commits the entry after obtaining a majority.
9. The committed operation is applied to the leader's state machine.
10. The gateway returns the booking result.
11. Email notification is queued after successful commitment and application.
The system uses majority-based commitment to maintain distributed consistency.

For a seven-node cluster:

- Total nodes: 7
- Majority required: 4
- Maximum unavailable nodes while retaining a majority: 3

# 4. Project Folder Structure
The main project structure is:

```
AOS_NEW_PYTHON/
│
├── backend/
│   ├── grpc/
│   │   └── proto/
│   │       ├── raft_pb2.py
│   │       └── raft_pb2_grpc.py
│   │
│   ├── raft/
│   │   └── node_runner.py
│   │
│   └── main.py
│
├── frontend/
│
├── llm/
│   ├── proto/
│   │   ├── llm_pb2.py
│   │   └── llm_pb2_grpc.py
│   │
│   └── llm_service.py
│
├── docs/
│   ├── architecture-audit.md
│   ├── implementation-report.md
│   └── migration-recovery-report.md
│
├── .env
├── .env.example
├── .gitignore
│
├── app.py
├── requirements.txt
├── pytest.ini
├── README.md
├── STARTUP_GUIDE.md
│
├── setup.bat
├── start_backend.bat
├── start_frontend.bat
├── start_raft_node.bat
├── start_all_raft_nodes.bat
├── stop_raft_nodes.bat
└── run_tests.bat
```

### Folder Descriptions
**backend/**

Contains the Python REST backend, booking-related operations, database integration, Raft gateway, and gRPC communication.

**backend/raft/**

Contains the Raft node implementation and node execution logic.

**backend/grpc/proto/**

Contains generated Python gRPC protocol files for Raft communication.

**frontend/**

Contains frontend-related application components.

**llm/**

Contains the LLM support service and its gRPC integration.

**llm/proto/**

Contains generated Python gRPC protocol files for LLM communication.

**docs/**

Contains architecture audits, implementation reports, and migration/recovery documentation.

**app.py**

Main Streamlit application entry point.

**requirements.txt**

Contains Python project dependencies.

**.env**

Contains local environment variables, credentials, database connection strings, and service configuration. It must never be committed to GitHub.

**.env.example**

Provides a template for configuring environment variables.

**STARTUP_GUIDE.md**

Contains additional development and startup instructions.

# 5. Installation and Environment Setup

## 5.1 Prerequisites
Install the following:

- Python 3.11 or compatible project-supported version.
- MongoDB Atlas account or a MongoDB deployment supporting transactions.
- Git.
- Visual Studio Code.
- Groq API key for LLM provider responses.
- SMTP credentials for email notifications.

## 5.2 Clone the Repository

```
git clone https://github.com/PUJARI-SAIBALAJI/BOOKING_DISTRIBUTED_SYSTEM.git

cd BOOKING_DISTRIBUTED_SYSTEM
```

## 5.3 Create Virtual Environment

```
py -m venv .venv
```
Activate it in Git Bash:

```
source .venv/Scripts/activate
```
Alternatively, in PowerShell:

```
.\.venv\Scripts\Activate.ps1
```

## 5.4 Install Dependencies

```
python -m pip install -r requirements.txt
```

## 5.5 Configure Environment Variables
Create a local `.env` file using `.env.example` as the reference.

Configure the following:

- MongoDB connection strings.
- Standalone database name.
- JWT secret.
- Groq API key.
- SMTP host and credentials.
- Raft node database connections.
- Raft node addresses and ports.
- Cluster size.
- REST API and LLM service ports.
Never upload the actual `.env` file to GitHub.

# 6. Database Architecture
FlashReserve uses MongoDB for standalone and distributed persistence.

## 6.1 Normal Mode Database
Database name:

`flashreserve`

This database stores standalone application data, including:

- Events.
- User accounts.
- Bookings.
- Payments.
- Notifications and email outbox.

## 6.2 Raft Mode Databases
The seven Raft nodes use separate MongoDB databases.

Raft NodeDatabaseNode 1flashreserve_raft_node1Node 2flashreserve_raft_node2Node 3flashreserve_raft_node3Node 4flashreserve_raft_node4Node 5flashreserve_raft_node5Node 6flashreserve_raft_node6Node 7flashreserve_raft_node7Each node has its own configured MongoDB connection.

**Important:** Separate databases provide persistence isolation, not automatic replication. Raft log entries and committed commands are replicated through gRPC communication.

All seven nodes may use the same MongoDB Atlas cluster, but their database names must be distinct.

The account store and notification outbox are shared through the standalone database. Therefore, the two operating modes are not fully independent for authentication and email delivery.

# 7. Running the Application
Open multiple terminals in VS Code.

Activate the same virtual environment or use the virtual environment's Python executable directly.

The following commands use the Git Bash terminal on Windows.

## 7.1 Terminal 1 – Start the Streamlit Frontend

```
./.venv/Scripts/python.exe -m streamlit run app.py --server.headless true --server.port 8502
```
Frontend URL:

[http://localhost:8502](http://localhost:8502)

## 7.2 Terminal 2 – Start the Python REST Backend

```
./.venv/Scripts/python.exe -m backend.main
```
Default backend health endpoint:

[http://127.0.0.1:5000/api/health](http://127.0.0.1:5000/api/health)

## 7.3 Terminal 3 – Start the LLM Service

```
./.venv/Scripts/python.exe -m llm.llm_service
```
Default LLM gRPC address:

`127.0.0.1:50060`

The LLM service communicates with the Groq provider when configured. If the provider is unavailable or not configured, a labelled FAQ fallback is returned.

# 8. Starting the Seven Raft Nodes
FlashReserve uses seven independent Python Raft processes.

Each node participates in leader election, log replication, commitment, and fault-tolerance operations.

There are two ways to start the cluster.

## Method 1: Start All Seven Nodes Automatically
Open a separate terminal and run:

```
./start_all_raft_nodes.bat
```
This script checks the configured node addresses, MongoDB URIs, and RPC ports before launching the seven processes.

The cluster must be configured with the same odd `RAFT_CLUSTER_SIZE` on every node.

For the current configuration:

`RAFT_CLUSTER_SIZE=7`

## Method 2: Start Nodes Individually
You can also launch each node separately.

Open seven terminals.

**Terminal 4 – Node 1**

```
./.venv/Scripts/python.exe -m backend.raft.node_runner --node node-1
```
**Terminal 5 – Node 2**

```
./.venv/Scripts/python.exe -m backend.raft.node_runner --node node-2
```
**Terminal 6 – Node 3**

```
./.venv/Scripts/python.exe -m backend.raft.node_runner --node node-3
```
**Terminal 7 – Node 4**

```
./.venv/Scripts/python.exe -m backend.raft.node_runner --node node-4
```
**Terminal 8 – Node 5**

```
./.venv/Scripts/python.exe -m backend.raft.node_runner --node node-5
```
**Terminal 9 – Node 6**

```
./.venv/Scripts/python.exe -m backend.raft.node_runner --node node-6
```
**Terminal 10 – Node 7**

```
./.venv/Scripts/python.exe -m backend.raft.node_runner --node node-7
```
Each process starts its corresponding Raft node using its configured node ID, MongoDB connection, and gRPC endpoint.

To stop an individually started node, use:

`Ctrl + C`

To stop the processes launched through the automatic startup script:

```
./stop_raft_nodes.bat
```

# 9. Raft Consensus Algorithm Implementation
The Raft implementation provides distributed coordination across seven nodes.

## 9.1 Node Roles
Every Raft node operates in one of three roles.

**Leader**

- Handles client write requests.
- Coordinates log replication.
- Sends heartbeats.
- Tracks follower acknowledgements.
- Commits log entries after majority replication.
**Follower**

- Receives heartbeats from the leader.
- Responds to voting requests.
- Receives replicated log entries.
- Acknowledges successful replication.
**Candidate**

- Starts an election when the election timeout expires.
- Requests votes from other nodes.
- Becomes leader after receiving majority votes.

## 9.2 Term Management
Raft uses terms to identify election periods.

Every election increments the term. Nodes use term information to reject outdated requests and maintain consistency.

## 9.3 Leader Election
When a follower does not receive heartbeats within its election timeout, it can become a candidate and initiate a leader election.

A candidate must obtain votes from a majority of the cluster to become leader.

## 9.4 Heartbeats
The leader periodically sends AppendEntries RPC messages to followers.

These messages maintain leadership and help followers remain synchronized.

## 9.5 Log Replication
When a client submits a booking operation:

1. The leader appends the operation to its log.
2. The leader sends the log entry to followers.
3. Followers validate and persist the entry.
4. Followers acknowledge successful replication.
5. The leader tracks acknowledgements.
6. The leader commits the operation after majority replication.

## 9.6 Majority Commitment
For seven nodes:

`Majority = floor(7 / 2) + 1 = 4`

The leader needs a majority of four nodes, including itself, to commit an entry.

## 9.7 Fault Tolerance
If the leader fails, the remaining nodes can elect a replacement leader if a majority is available.

The new leader continues the distributed operation according to Raft's log consistency rules.

The implementation includes recovery-related mechanisms, but snapshot installation is not implemented. Production-grade recovery should not be assumed.

# 10. Live Raft Monitoring
The application includes a live Raft cluster monitor on the sign-in/create-account screen.

The monitor displays cluster information such as:

- Node identity.
- Node status.
- Current leader.
- Follower status.
- Election term.
- Quorum information.
- Database connectivity.
- Log and replication information.
- Per-follower replication acknowledgements.
Replication acknowledgement states include:

- ACKNOWLEDGED
- PENDING
- FAILED
- CATCHING UP
- UNREACHABLE
The monitor provides visibility into the distributed cluster and its replication activity.

Detailed log, commit, application, and recovery information remains available in node details.

# 11. Booking and Reservation Features
FlashReserve provides an end-to-end ticket booking workflow.

## 11.1 Event Management

- Display available events.
- View event details.
- Maintain separate event catalogues for Normal and Raft Modes.
- Select events before booking.

## 11.2 Seat Selection

- Display the complete seat layout.
- Identify available and reserved seats.
- Allow users to select seats.
- Validate availability before booking.

## 11.3 Concurrent Booking
The backend validates booking requests to prevent conflicting reservations.

Normal Mode uses its standalone database transaction workflow.

Raft Mode submits write operations through the Raft leader and majority-commitment workflow.

## 11.4 Mock Payment Processing
The application includes mock/stub payment processing.

It simulates the payment workflow without integrating a production payment gateway.

## 11.5 Booking Management
Users can:

- Create bookings.
- View booking details.
- View booking status.
- Cancel bookings.
- Receive booking confirmation notifications.

# 12. Email Notification Service
FlashReserve includes an additional email notification feature for booking and cancellation events.

The system uses SMTP with STARTTLS.

## 12.1 Booking Confirmation Email
When a user successfully books tickets and the mock payment confirms the booking:

1. The backend completes the booking operation.
2. A notification is queued.
3. The notification worker processes the queued email.
4. An email is sent to the signed-in user's registered email address.

## 12.2 Booking Cancellation Email
When a user cancels a booking:

1. The cancellation operation is processed.
2. In Raft Mode, the operation must be committed and applied first.
3. The notification is queued.
4. The email worker processes the cancellation notification.
5. A cancellation email is sent to the user's registered email address.

## 12.3 SMTP Configuration
Configure these environment variables in `.env`:

```
SMTP_HOST=
SMTP_PORT=
SMTP_USER=
SMTP_PASSWORD=
SMTP_FROM_NAME=
```
The backend uses SMTP STARTTLS to send emails.

**Important implementation details:**

- The destination is the signed-in user's email address, not the SMTP username.
- Notification delivery metadata is stored in the standalone `notificationoutbox` collection.
- Both Normal Mode and Raft Mode use this shared outbox.
- Queue entries are deduplicated by operating mode, booking ID, and notification type.
- Failed deliveries are logged and retried.
- Ambiguous sending attempts can be marked `delivery_unknown` to avoid automatic duplicate emails.
- SMTP acceptance does not guarantee that an email reaches the recipient's inbox.
The booking operation and notification queue insertion are not part of one atomic transaction. If the application stops between these operations, an email may not be queued until the booking operation is retried.

This notification service is an additional application feature, not a production-grade exactly-once email delivery system.

# 13. LLM-Powered Customer Support
FlashReserve integrates an LLM-powered customer support chatbot.

The chatbot helps users with common booking questions.

Example questions:

- How can I cancel my booking?
- Which seats are available?
- How does the booking process work?
- How can I view my reservation?
- What happens after payment?

## Architecture

```
             STREAMLIT FRONTEND
                     |
                     v
                LLM CLIENT
                     |
                     v
                gRPC SERVICE
                     |
                     v
                 GROQ API
                     |
                     v
              GENERATED RESPONSE
```
Configuration:

```
GROQ_API_KEY=
GROQ_MODEL=
LLM_GRPC_HOST=127.0.0.1
LLM_GRPC_PORT=50060
```
If the Groq provider is not configured or unavailable, the service returns a labelled FAQ fallback.

# 14. Testing
FlashReserve includes automated tests for the backend, distributed functionality, and other application components.

Run the complete test suite:

```
./.venv/Scripts/python.exe -m pytest -q
```
Alternatively:

```
./run_tests.bat
```
The automated tests use fake MongoDB components and do not write to the configured database, send actual emails, or make paid provider requests.

For detailed implementation and verification information, refer to:

- `docs/architecture-audit.md`
- `docs/implementation-report.md`
- `docs/migration-recovery-report.md`

# 15. Important Implementation Limitations
The following limitations should be considered before deployment:

1. Payment processing is mocked; no production payment gateway is integrated.
2. SMTP delivery is not guaranteed exactly once.
3. The account store and email notification outbox remain shared between the two operating modes.
4. Snapshot installation is not implemented in the Raft cluster.
5. Raft Mode should undergo additional failure-injection and recovery testing before production deployment.
6. The current implementation is intended for academic demonstration and development, not production ticketing workloads.

# 16. GitHub Repository
**Repository:**
[https://github.com/PUJARI-SAIBALAJI/BOOKING_DISTRIBUTED_SYSTEM](https://github.com/PUJARI-SAIBALAJI/BOOKING_DISTRIBUTED_SYSTEM)

Clone the project:

```
git clone https://github.com/PUJARI-SAIBALAJI/BOOKING_DISTRIBUTED_SYSTEM.git
```
The repository excludes local environment files and virtual environments through `.gitignore`.

# 17. Project Summary
FlashReserve combines a distributed ticket booking application with the Raft Consensus Algorithm.

The project demonstrates:

- Distributed systems architecture.
- Client-server communication.
- REST API development.
- gRPC communication.
- Leader election.
- Heartbeats.
- Log replication.
- Majority commitment.
- Fault tolerance.
- MongoDB persistence.
- Concurrent booking management.
- Mock payment processing.
- LLM integration.
- SMTP-based email notifications.
The project demonstrates how distributed consensus can be applied to a practical ticket reservation scenario to coordinate booking operations across multiple nodes.

---

**FlashReserve – Distributed Ticket Booking System**

*Built with Python, Streamlit, MongoDB, gRPC, Raft Consensus, and LLM Integration.*