"""The supported, provider-free local application construction boundary."""
from __future__ import annotations

import platform
import re
import sys

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

from runtime.local_session import LocalSession
from runtime.resources import ResourceResolver
from services.athena_capability_service import AthenaCapabilityService, release_summary


class AppFactoryError(ValueError):
    """Trusted local application dependencies failed verification."""


def create_app(*, release_identity, resource_resolver, local_session, capability_service, origin):
    if (type(resource_resolver) is not ResourceResolver
            or resource_resolver.identity is not release_identity
            or type(local_session) is not LocalSession
            or type(capability_service) is not AthenaCapabilityService
            or capability_service.resources is not resource_resolver
            or type(origin) is not str
            or not re.fullmatch(r"http://127\.0\.0\.1:[1-9][0-9]{0,4}", origin)):
        raise AppFactoryError("invalid trusted application dependencies")
    if not 1 <= int(origin.rsplit(":", 1)[1]) <= 65535:
        raise AppFactoryError("invalid loopback endpoint")
    if sys.platform != "win32" and not sys.platform.startswith("linux"):
        raise AppFactoryError("unsupported local runtime platform")
    if sys.version_info[:2] != (3, 12) or platform.python_implementation() != "CPython":
        raise AppFactoryError("unsupported local runtime interpreter")
    try:
        release = release_summary(release_identity)
        assets = {url: resource_resolver.read_bytes(path, expected_role="UI")
                  for url, path in (("/", "ui/index.html"), ("/app.js", "ui/app.js"),
                                    ("/styles.css", "ui/styles.css"))}
        capability_service.snapshot()
        local_session.credential()
    except Exception:
        raise AppFactoryError("trusted application resources could not be verified") from None
    app = FastAPI(title="ATHENA Research Preview", docs_url=None, redoc_url=None, openapi_url=None)
    host = origin.removeprefix("http://")

    @app.middleware("http")
    async def security(request: Request, call_next):
        hosts = request.headers.getlist("host")
        tokens = request.headers.getlist("x-athena-session")
        if hosts != [host]:
            return JSONResponse({"error": "invalid_local_host"}, status_code=403)
        # Verified public assets contain no credential or authority snapshot.
        protected = request.url.path not in assets or request.method not in {"GET", "HEAD"}
        authenticated = len(tokens) == 1 and local_session.accepts(tokens[0])
        proofs = request.headers.getlist("x-athena-handshake")
        if request.url.path == "/api/v1/health" and request.method == "GET" and not tokens:
            authenticated = len(proofs) == 1 and local_session.accepts_handshake(proofs[0])
        if protected and not authenticated:
            return JSONResponse({"error": "invalid_local_session"}, status_code=401)
        origins = request.headers.getlist("origin")
        if origins and origins != [origin]:
            return JSONResponse({"error": "invalid_local_origin"}, status_code=403)
        if request.method not in {"GET", "HEAD"} and origins != [origin]:
            return JSONResponse({"error": "invalid_local_origin"}, status_code=403)
        response = await call_next(request)
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "no-referrer"
        response.headers["Content-Security-Policy"] = (
            "default-src 'none'; script-src 'self'; style-src 'self'; connect-src 'self'; "
            "img-src 'self'; frame-ancestors 'none'; base-uri 'none'; form-action 'none'")
        return response

    @app.get("/api/v1/health")
    def health(request: Request):
        if (request.headers.getlist("x-athena-instance") != [local_session.instance_id]
                or request.headers.getlist("x-athena-challenge") != [local_session.challenge]):
            return JSONResponse({"error": "invalid_local_challenge"}, status_code=403)
        return {"contract": "ATHENA_LOCAL_HEALTH_V1", "instance_id": local_session.instance_id,
                "challenge": local_session.challenge, "server_proof": local_session.proof("server"), "release": release,
                "runtime": {"platform": sys.platform, "python": platform.python_version()},
                "resources": "verified_snapshot", "provider_authority": False,
                "model_readiness": "unproven"}

    @app.get("/api/v1/capabilities")
    def capabilities():
        try:
            return capability_service.snapshot()
        except Exception:
            return JSONResponse({"error": "local_evidence_unavailable"}, status_code=503)

    for url, payload in assets.items():
        media = "text/html" if url == "/" else "text/javascript" if url.endswith(".js") else "text/css"

        # Closure values never appear as user-controlled query dependencies.
        def make_asset(data, content_type):
            def serve():
                return Response(data, media_type=content_type)
            return serve

        app.add_api_route(url, make_asset(payload, media), methods=["GET", "HEAD"])
    return app
