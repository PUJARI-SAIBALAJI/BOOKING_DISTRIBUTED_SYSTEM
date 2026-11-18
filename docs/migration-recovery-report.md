# FlashReserve migration recovery report

## Recovery evidence

The workspace has no Git repository metadata, so its prior commits and
branches cannot be inspected. No original application JavaScript source was
found in the project source tree; JavaScript files under the Python virtual
environments are third-party package assets and are not an application
reference. Consequently, the pre-migration API and database contract cannot
be verified against the original backend. The recovery comparison below is
limited to the current Streamlit API client, Python REST routes, models,
services, and tests.

The Python application uses **events**, not movies/shows, as its catalogue
entity. Existing frontend actions call `/api/events`, seat-reservation,
booking, mock-payment, cancellation, chat, and administrator endpoints. No
separate show entity or movie/show endpoint was found.

## Current Python feature recovery

| Capability | Current evidence | Recovery status |
|---|---|---|
| Streamlit client and existing pages | Existing event, seat, booking, payment, support, profile, and admin pages call the centralized `frontend.utils.api` client. | Login screen rendered in a browser; its normal-mode API client completed the live smoke flow below. No signed-in browser journey was run. |
| Authentication | Registration hashes passwords and forces the customer role; login returns a JWT. Protected routes authorize from the token. | Present in Normal Mode. Raft-mode account creation/replication is not implemented. |
| Event catalogue and seats | Event and seat models/services support listing, administration, holds, and seat availability. | Present in Normal Mode. These writes/holds are not Raft log commands. |
| Booking, payment, cancellation | Service layer enforces reservation and amount validation, uses mock payments, idempotency keys, and cancellation/refund behavior. | Present in Normal Mode; transaction-backed workflows need a transaction-capable MongoDB server. |
| Administrator UI/API | Admin dashboards and protected event/user/booking/seat routes exist. Public registration cannot set an admin role. | Admin account provisioning/login setup is not implemented; protected routes require an already provisioned admin account. |
| Raft | Python gRPC RequestVote, AppendEntries, SubmitCommand, and status RPCs plus an HTTP gateway exist. The frontend routes Raft-mode booking operations through the gateway. | Isolated seven-node gRPC test committed/applied commands and elected a replacement leader after leader loss. Mongo-backed booking/payment workflows, persistent restart recovery, and snapshot installation remain unverified or unsupported. |
| LLM | Python gRPC support service, Groq integration, and FAQ fallback exist. | Model validation and one real support question through the local gRPC service passed. |
| SMTP | No durable notification/outbox implementation was found. | Gmail STARTTLS authentication passed; no email was sent and no sender/outbox/retry worker exists. |
| Original Node.js comparison | No Git history or original backend source is available in this workspace. | Exact lost-feature comparison cannot be established. |

## Live Normal Mode smoke test

A temporary database (created and dropped for the test) was used with a real
local Uvicorn server and the existing Streamlit API client. Health, user
registration/login, event and seat reads, seat reservation, booking, mock
payment, booking history, and cancellation all passed. The test did not use the configured standalone application database. The
payment route is a mock-payment flow, not a real payment processor.

## Configuration evidence

The local `.env` contains standalone MongoDB, JWT, seven per-node Raft
database URIs, SMTP, and Groq settings. Secret values are intentionally not
reproduced. All seven Raft URI pings succeeded; each uses a distinct database
name on the same Atlas cluster host, not a separate MongoDB deployment.
Backend startup connected to `flashreserve` and initialized compatible
indexes. The Normal Mode CRUD/transaction workflow above used a temporary
database; no booking was written to the configured application database.

The backend accepts `PORT` with legacy `APP_PORT` fallback,
`STANDALONE_DB_NAME` with legacy `DATABASE_NAME` fallback, and the standalone
URI names `STANDALONE_MONGO_URI`/`MONGODB_URI`. The frontend accepts
`API_BASE_URL` and retains its previous normal API URL names.

## Current runtime verification

- Backend health endpoint returned HTTP 200 with status `ok` and database
  `flashreserve` connected.
- Streamlit rendered its login page on port 8502. Port 8501 belongs to another
  project and was left untouched.
- Seven updated Raft gRPC processes answered status checks. All report healthy
  databases and matching topology; node-6 is leader with seven acknowledgements
  for the four-node majority. Every node reports the pre-existing log, commit,
  and applied index 133. No client command was submitted to Atlas.
- Groq model check and one live gRPC support question passed.
- Gmail STARTTLS authentication passed; no email was sent.
- Backend and LLM tests: **212 passed**, one Starlette/httpx deprecation warning.
- Python compilation and `pip check` passed.

## Remaining recovery work

1. Obtain the original backend source or Git history to verify endpoint,
   validation, payment, and schema compatibility.
2. Verify Mongo-backed booking, payment, cancellation, and concurrent seat
   reservation through the Raft gateway using an isolated disposable cluster.
3. Implement and test snapshot installation and persistent restart recovery;
   verify idempotency and follower catch-up after process loss.
4. Implement the durable SMTP outbox and secure initial administrator
   provisioning.
5. Deploy Raft nodes against independent MongoDB endpoints and run
   multi-process failure, recovery, and overbooking tests.
6. Run browser-based UI workflows and Raft integrations only against a
   disposable test database and explicitly configured SMTP/LLM test
   credentials.
