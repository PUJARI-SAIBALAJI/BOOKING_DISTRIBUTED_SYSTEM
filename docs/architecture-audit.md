# FlashReserve architecture audit

## Parallel elections and node observations, 2026-11-18

The vote requests described as sequential in the earlier section now run
independently with bounded gRPC deadlines. A majority can elect a leader
without waiting for a slow peer. A later higher-term response still makes the
node step down; votes from a different election term are not counted.
RequestVote, AppendEntries, and node status RPC failures now log the actual
gRPC status, details, debug string, endpoint, timeout, and channel state.
Node terminals show periodically sampled peer status independently of Raft
processing; a status RPC failure is not proof that the peer process stopped.

On an isolated node 1, real RequestVote failures to `127.0.0.1:50052` and
`127.0.0.1:50053` reported `UNAVAILABLE`, with Windows connection-refused
details. The other six nodes were intentionally not running during that
sample. This does not establish the causes of the user's earlier errors.
When all seven test processes ran, node 1 was observed as leader in term 6842
with four votes, and all followers reported the same leader, term, and
log/commit/applied indexes of 145 in their respective configured databases.
After node 1 was stopped, node 5 became leader in term 6843 with four votes.
A unique diagnostic READ_BARRIER committed at index 146; node 1 was restarted
and all seven nodes reported log/commit/applied indexes of 146. No booking was
created in this particular check. The barrier remains in the Raft log.

Another seven-process observation produced five sampled cluster tables per
node over approximately 27 seconds, with no status-monitor errors. In a node 1
sample all seven reported term 6844 and node 2 as leader. These test-created
processes were stopped after the checks. The regression suite passed 254 tests
with one existing deprecation warning. The separate MongoDB persistence writes,
crash safety, snapshot installation, network partitions, and authenticated
frontend booking after leader failure remain unverified or unsupported.
No independent retry/backoff policy was added within each RPC; later election,
heartbeat, and monitoring rounds provide subsequent bounded attempts.

## Election and duplicate-start investigation, 2026-11-18

The original Node 1 timeout output does not establish whether the other nodes
were available or why its elections failed. The original owner of Node 5's
port was not captured; port 50055 was free when checked for this investigation.

The election monitor previously checked the timeout and started an election in
separate critical sections. A heartbeat between those operations could cause an
unnecessary election. Timed elections now recheck the timeout while holding the
node lock. Votes with a response term different from the election term are no
longer counted, and a candidate transitions when it receives a majority rather
than waiting for all remaining sequential requests. At the time of this
earlier test, vote requests were still sequential. MongoDB
persistence failures and interrupted multi-collection writes remain unresolved.

In a live test with the existing Atlas configuration, all seven processes
reported their distinct expected databases and converged on node 1 as leader
in term 6831. A second status sample 10 seconds later showed the same leader,
term, and log/commit/applied indexes of 145 on every node. A duplicate node 5
process exited with a port-50055 bind-conflict error, while the first remained
running. After the test stopped node 1, the other six converged on node 5 as
leader in term 6833, with indexes still at 145. This was an election test: no
booking was created during it. A prior unmodified-code observation was stable
for approximately one minute after startup. Neither observation establishes
long-term stability or crash safety. All test-created processes were stopped.

The new timer, stale-vote, early-majority, and occupied-port regressions passed;
the complete suite passed 251 tests with one existing deprecation warning.
Per-node process locking, independent parallel vote requests, full lifecycle
and monitoring events, actual booking after leader failure, and the frontend
Raft booking path still need work or verification. The referenced PDFs were
not present in the workspace or current attachments.

## Live Raft booking and recovery check, 2026-11-18

Seven separate node processes used the existing configured Atlas databases and
real gRPC communication. A uniquely labelled test event and synthetic user ID
were used; no customer records were modified and no email was sent. The test
submitted commands through the Python Raft gateway directly, not through an
authenticated HTTP or Streamlit session.

- A reservation, booking, successful mock payment and cancellation committed;
  the resulting booking appeared on all seven nodes with the expected status.
- While one follower was stopped, a second booking committed and appeared on
  the six running nodes. The restarted follower caught up and applied it.
- The leader was stopped; a different node won election in a higher term and
  committed a read barrier. This verifies failover, not a new booking after
  leader failure.
- With three nodes stopped, a new booking committed and appeared on the four
  remaining nodes. Repeating the same command returned the same booking ID.
  With four nodes stopped, a direct gRPC command returned `committed=false`
  and the gateway rejected a new command with `RAFT_NO_QUORUM`. After restart
  the booking appeared once in each of the seven databases.
- The first two test bookings were absent from the standalone database. At the
  later check, each node had exactly one copy of each of the three test
  bookings and reported persisted commit/applied indexes of 144. The test event
  was subsequently archived through a committed Raft command. Test records
  remain, and the test node processes were stopped.

The test found that reservation expiry was based on each replica's local
application time. Reservations now use the replicated command timestamp,
including on follower catch-up; Normal Mode keeps using the local clock.
This fix is covered by targeted tests and by the live booking workflow.
This is not a proof of crash-safe persistence or exhaustive Raft safety.
Mongo-backed log, metadata and applied-result writes remain separate
operations; interrupted writes and network partitions need further testing.
Snapshot installation is still unsupported. The runtime now logs actual
election, replication acknowledgement and application events with timestamp,
node, term, state and indexes, but not every requested lifecycle event.
Full regression suite: 247 passed, with one existing deprecation warning.

## Raft safety review, 2026-11-18

The existing deployment uses `backend.main` as the REST gateway and
`backend.raft.node_runner` as the independent node entrypoint. Its gRPC
contract is `backend/grpc/proto/raft.proto`; each node opens its configured
database through `backend/database/raft_database.py`. Normal Mode uses the
standalone MongoDB handle. The gateway submits Raft reservation, booking,
mock-payment and cancellation commands to the leader; application happens
on each node through `RaftStateMachine`. The original JavaScript backend and
the two requested lecture/paper attachments were not available in the
workspace for comparison.

The review reproduced and fixed three safety problems:

1. A follower advanced its commit index through a divergent suffix not
   covered by the accepted AppendEntries request.
2. A malformed AppendEntries request with a higher term could be rejected
   without persisting that term and cleared vote.
3. An old replication response could update progress after a node had become
   leader in a later term.

Regression tests cover these cases, including ensuring commit index never
decreases. The complete suite passed 245 tests. A startup log now reports
the actual node, selected database, port, term, role and indexes.

Important remaining limitations: `MongoRaftStore.save` writes logs, applied
results and metadata in separate operations, so crash/interrupted-write
recovery across these operations has not been established. A persistence
exception can also leave in-memory state changed, which has not been
demonstrated safe under retries. Snapshot installation is not implemented.
The earlier review had not performed real booking replication, cancellation,
follower catch-up or minority tests; see the later check above. In particular,
unit/in-memory tests do not establish persistent
state-machine safety or prove that this implementation is production-ready.
Node event logging remains incomplete and is not uniformly structured.

The earlier seven-process election/failover test is documented in the
[implementation report](implementation-report.md); it did not submit a
booking and does not verify these safety properties.

## Scope and evidence

This audit covers the Python backend, Streamlit entry point and REST client,
Raft/gRPC implementation, MongoDB configuration, LLM service, dependency
manifests, and tests. `.env` values were not printed. The current backend test
suite has **212 passing tests**.

## Current findings

| Area | Finding and status | Evidence |
|---|---|---|
| Normal-mode REST backend | **Running and live-smoke-tested.** The API health endpoint returns 200 and reports the configured `flashreserve` database connected. A disposable-database flow passed registration/login, event and seat reads, reservation, booking, mock payment, history, and cancellation. | `backend/api.py`, `backend/main.py`, `frontend/utils/api.py` |
| Streamlit frontend | **Running on port 8502.** Its login page rendered in the browser. Port 8501 is a different project and was not touched. | `app.py`, `frontend/` |
| MongoDB index compatibility | **Fixed and tested.** Startup initially failed because pre-existing Atlas indexes had legacy names/options. Python index definitions now reuse compatible legacy index names and the existing partial uniqueness condition. | `backend/database/mongodb.py`, `backend/raft/mongo_raft_store.py`, `backend/tests/test_mongodb_indexes.py` |
| Raft database topology | **Seven logical DBs reachable, not seven independent MongoDB deployments.** All seven URIs passed ping and use distinct configured DB names on the same Atlas cluster host. | `backend/config.py`, `backend/database/raft_database.py` |
| Raft gRPC and election | **Live smoke-tested after restarting the updated services.** All seven nodes report healthy, connected databases, and matching topology. Node-6 is the leader with seven quorum acknowledgements; all nodes report the persisted log/commit/applied index 133. No application command was submitted to Atlas. | `backend/raft/grpc_transport.py`, `backend/raft/raft_node.py`, `backend/raft/http_gateway.py` |
| Raft HTTP gateway/booking | **Gateway and gRPC command path implemented; business integration remains unverified.** Isolated seven-node tests committed/applied a test command and elected a replacement leader after stopping the first. Mongo-backed booking/payment commands have not been tested end to end; snapshot installation/recovery is unsupported. | `backend/raft/http_gateway.py`, `backend/raft/grpc_transport.py`, `backend/raft/state_machine.py`, `frontend/utils/api.py` |
| LLM | **Live tested.** Configured Groq model availability check passed and a support question returned a nonempty `ok` response via the local Python gRPC service. | `llm/llm_service.py`, `backend/api.py` |
| SMTP | **Authentication only.** Gmail STARTTLS login passed; no email was sent. The code has no notification sender, durable outbox, or retry worker. | Backend source inventory |
| Administrator | Protected administrator routes exist. Secure initial account provisioning is not implemented. | `backend/api.py`, `backend/services/auth_service.py` |
| Original migration recovery | No Git repository metadata or original JavaScript backend source is available, so exact source-to-source contract comparison cannot be done. | Workspace inventory |

## Configuration and infrastructure

Seven unique Raft database names and URI paths are configured. All resolve to
one Atlas cluster endpoint, so they are logically separate databases on a
shared cluster—not independent MongoDB servers. Admin provisioning settings
are absent. The local cluster uses `127.0.0.1` RPC addresses and is only a
single-machine topology.

Backend startup created/verified indexes in the configured standalone DB and
the Raft nodes loaded persisted state. The Raft databases already report
matching log/commit/applied index 133. Their contents were not read or changed
by submitting a command. A prior Normal Mode integration test used a temporary
database, which was dropped. No email was sent; one simple support question
was sent to Groq.

## Verification

- Current backend and LLM suite: **212 passed**, one Starlette/httpx warning.
- Python compilation and `pip check`: passed.
- Backend `http://127.0.0.1:5000/api/health`: HTTP 200, status `ok`, database connected.
- Raft status and leader endpoints: HTTP 200; 7/7 nodes healthy, 7/7 databases connected, 7/7 topologies matched, and a quorum-confirmed leader.
- Streamlit: running at `http://127.0.0.1:8502/`.
- The live Streamlit page displays “Backend connected”; its refresh button reran the health check successfully.
- Raft gRPC: 7/7 nodes answered; one leader observed in the sampled term.
- Isolated seven-node gRPC integration: command commitment/application across seven in-memory nodes, then replacement-leader commitment across six remaining nodes.
- Groq model validation and one real gRPC question: passed.
- SMTP STARTTLS authentication: passed; no email sent.

These results do **not** establish Mongo-backed Raft booking writes,
persistent restart recovery, concurrency/overbooking protection, SMTP
notification delivery, or independent MongoDB cluster availability. The
live connectivity probe did not create bookings or send mail; no dedicated
SMTP delivery test was found. See the
[implementation report](implementation-report.md)
and [migration recovery report](migration-recovery-report.md).
