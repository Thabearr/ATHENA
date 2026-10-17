# RUN-02A Current Shadow operation fence

## Authority and cancellation contract

The coordinator-owned worker startup gate proves one exact run, attempt, lease,
release, and process owner. It does not authorize every later provider request.
The Current Shadow supervisor receives a bounded canonical capability file in
the admitted run directory. Its child authenticates that file against the same
app database, startup gate, current attempt, release identity, data root,
parent process, and a durable child-start event before it enters the runner.
Environment variables and argv select this path; neither grants authority.

Supervisor creation is ordered with `CANCEL_REQUESTED` by a short app-store
write transaction. The child is started with its stdin held and cannot proceed
until the parent commits the exact child-start event and releases the pipe. If
cancellation commits first, the supervisor is not spawned. If the start
transaction commits first, the child must still revalidate `RUNNING` before
starting and every provider operation independently revalidates the owner and
run state.

Every product Current Shadow GET has one immutable `PREPARED` request record
and one single-use `SENT` authorization. Both transitions use the existing
app-store writer lock and SQLite `BEGIN IMMEDIATE`, which also serializes with
durable cancellation. A cancel that commits before `SENT` rejects the request
before transport invocation. A `SENT` commit that wins first is one in-flight
attempt: the OS can pause the process after that commit and before the first
network byte, so this design does not claim that physical HTTP bytes can never
leave after a later cancellation commit. No second operation is authorized
after cancellation. Redirects, transport retries, and automatic restart are
denied.

Raw response bytes and bounded response metadata are retained with the exact
request intent before parsing. The operation is `CONFIRMED` only after those
bytes are durably published and linked. A crash after `PREPARED` is proven
not-sent because code cannot reach transport without `SENT`; recovery records
that no-send disposition. A crash after `SENT`, or between response receipt,
file publication, and DB confirmation, remains `OUTCOME_UNKNOWN`. Recovery
never repeats a GET or infers a response from a process exit.

Short local evidence publications also revalidate the child and `RUNNING`
inside a short app-store transaction. They do not hold that transaction across
provider I/O or the 75-minute supervisor. A response already authorized by a
committed `SENT` may be retained after cancellation as in-flight evidence; it
does not authorize another GET or business completion.

## Trust and scope

The capability contains a lease digest, never the lease token. The child also
validates the HMAC-authenticated startup gate using the durable lease retained
in the app store. The canonical capability bytes are published once beneath
the exact run directory with owner-only file permissions and are bound to the
child PID/process-start identity by the durable event. This protects against
forged, stale, cross-run, and accidental replayed local files. A malicious
process running as the same OS user can read or alter that user's SQLite store
and is outside the local same-user filesystem threat model; file permissions
and a digest are not claimed to defeat that actor.

## Product acquisition call graph

The admitted `CURRENT_SHADOW_REQUEST` reaches four reviewed external GET
families. Product mode routes each through the same authority port:

1. `domain.current_shadow_all_market_runner.acquire_current_shadow_pre_router_bundle`
   calls `_issue_current_fixture_sources` or `_issue_exact_fixture_sources` for
   each selected date. Those loops reach
   `scripts.issue_current_fotmob_reviewed_source.issue_current_shadow_fotmob_reviewed_source`
   and `scripts.capture_fotmob_data_matches.fetch_fotmob_data_matches`.
   Each date's FotMob GET has its own validated request intent and permit.
2. The same bundle calls
   `domain.current_shadow_sportybet_pc_upcoming_reconciliation.capture_current_upcoming_discovery`
   (the runner-compatible seam). It delegates to
   `capture_current_pc_upcoming_discovery`, whose bounded epoch/page loop calls
   `domain.current_shadow_sportybet_pc_upcoming_discovery._fetch_page` once per
   page. Each page and capture epoch is a separate GET identity and permit.
3. Reconciliation may call
   `domain.sportybet_live_event_quote_evidence.capture_live_event_quote_evidence`
   for an individual event; `_network_fetch` validates the event ID and uses
   one separate GET permit for that event detail request.
4. When matched fixtures require durable fresh history, the bundle calls
   `domain.current_fotmob_latest_durable_fresh_history.build_current_fotmob_latest_durable_fresh_history_handoff`.
   Its fixed PR151 readers cover the main ref, workflow-run pages, run
   metadata, artifacts, jobs, releases, Actions artifact ZIPs, and release
   assets. Product mode uses the authority port for every API request and
   download hop. An artifact or release redirect is validated against the
   fixed HTTPS host set and recorded only as a URL digest; its follow-up GET
   receives its own permit. The signed query and `GH_TOKEN` are not written to
   run events or artifacts. Direct non-product research callers retain their
   existing GitHub CLI readers.

No share-code CREATE/reload transport is reachable from this product request;
admission requires `create_share_code=false`, and the fixed nested argument
does too. The direct PORT-02C installed-release identity qualification remains
outside product admission only when the authenticated installed identity, exact
offline operation/request, and fixed `data_root/port02c-runs/<request-sha>` path
all match. It cannot enter Current Shadow acquisition.

Existing direct research callers retain their previously reviewed transport
path. The standalone installed PORT-02C identity probe remains its separate
fixed offline route. Share-code CREATE/reload, login, cookies, wallet,
staking, wagering, MAIN authority, and model/Router/Portfolio algorithms are
outside this change.

The adjacent legacy `current_shadow_sportybet_upcoming_reconciliation` and
`sportybet_current_event_discovery_reconciliation` modules still expose
separately reviewed direct-research capture functions, and
`_current_shadow_sportybet_catalog_fanout_reconciliation_base` has its own
research GET helper. They are not reached by this fixed product request:
the product runner imports the PC-upcoming reconciliation owner, calls its
PC capture seam above, and uses the adjacent modules only for retained parsing,
matching, and replay helpers. The product call graph does not call their
`_network_fetch_snapshot`, `_network_fetch_page`, `_network_get`, or capture
entrypoints. Those direct research APIs were left intact.
