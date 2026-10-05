# APP-01A local application shell

This shell exposes local health and capability information. Run preview,
admission, execution, provider acquisition and delivery remain outside its
authority. A capability snapshot is never an admission decision.

## Construction and resource trust

`api.app_factory.create_app` requires an exact verified release identity and
its resource resolver, one launch session and its capability service. It
serves verified byte snapshots of the three bundled UI resources. The
capability service parses the verified component authority registry using
the existing registry contract. It does not infer model readiness from
weights or model files. Windows and Linux CPython 3.12 are the qualified
runtime family used by the existing PORT-02C slice.

Development launch uses the explicit checkout containing `run_desktop.py`;
its resources must match committed HEAD. Installed launch requires:

```
athena-shell --release-root <absolute-release-root> --trusted-manifest-sha256 <trusted-pin>
```

The pin must come from the trusted caller. Reading a pin from unverified
release metadata would not establish trust. Installed execution uses the
PORT-02 verifier and never invokes Git or system Python.

The existing frozen `--port02c-smoke` invocation is retained: its release
root is derived from the frozen executable's reviewed bundle layout and
its trusted pin is supplied through the existing qualification caller's
`MANIFEST_SHA` environment value. The flag does not open a UI. Missing or
invalid pins fail closed. This is a qualification seam, not release signing.

## Session and bootstrap

Each launch generates a memory-only 256-bit CSPRNG credential, instance ID
and challenge. The OS assigns a loopback port to a socket held throughout
backend startup; the shell never adopts an existing responder.

The startup request sends a client HMAC proof without sending the session
credential. The server returns a distinct server HMAC proof. Verification
also requires the exact instance, challenge, release, build and runtime
contract before creating the UI window. Redirects are rejected.

The native window loads the verified backend origin. One native JavaScript
task checks the actual document origin and root path before delivering the
launch credential into a one-use UI function. That function removes itself
and keeps credentials in a closure. No Python API is exposed to JavaScript;
there is no shell, filesystem, environment, process or arbitrary fetch bridge.
The webview uses private mode and the backend denies caching. Credentials
are absent from URLs, browser storage, persistent configuration and logs.

## HTTP boundary

Host must equal the selected numeric loopback host and port. Health and
capabilities require session authentication; health additionally checks
instance and challenge. The narrowly scoped startup proof authenticates
only health. Mutations require the same session and exact same-origin
Origin before route execution. No CORS middleware is installed. The content
policy limits scripts, styles and connections to the backend origin.

Shutdown invalidates the session and stops the owned backend. It grants no
worker durability or recovery guarantee.

## Retained compatibility and evidence

`api.server` imports without constructing providers or a FastAPI app.
Explicit development compatibility constructs its retained API and legacy
routers. Original UI bytes are retained as `ui/legacy-index.html` and
`ui/legacy-app.js`, outside the supported installed resource allowlist.
Legacy status reports deprecated compatibility and unproven readiness.
The supported shell never navigates to or calls these provider routes.

A2 V10 extends immutable V1–V9. B7 and Completion V10 retain their exact
historical A2 V9 pin while authenticating the latest current corpus first;
a broken current inventory cannot fall back to historical evidence.
The APP-01A receipt binds semantic sources and base identities. Exact final
head/tree and automatic CI results are reported separately to avoid circular
commit or workflow-run identities in source-controlled receipts.

Rollback is a revert of the APP-01A semantic commit. No external side effect
or persisted launch credential requires recovery. Review readiness requires
green automatic Tests on the exact final head; this mission does not merge.
