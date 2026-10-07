"""Trusted local shell: verified resources, owned listener, no execution authority."""
from __future__ import annotations

import argparse
import json
import os
import platform
from datetime import datetime, timezone
from pathlib import Path
import socket
import sys
import threading
import time
import urllib.request

import uvicorn

from api.app_factory import create_app
from database.app_repository import AppRepository, release_provenance
from runtime.local_session import LocalSession
from runtime.release_identity import (
    DevelopmentCheckoutIdentity,
    InstalledReleaseIdentity,
    verify_development_checkout,
    verify_installed_release,
)
from runtime.resources import (
    ResourceResolutionError,
    ResourceResolver,
    WritableRoots,
    default_writable_roots,
)
from services.athena_capability_service import AthenaCapabilityService, release_summary
from services.athena_preview_service import AthenaPreviewAdmissionService
from services.athena_read_service import AthenaReadService
from services.app_preview_store import DurablePreviewStore


class DesktopLaunchError(ValueError):
    """Safe, fail-closed desktop startup failure."""


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description="ATHENA desktop shell.", allow_abbrev=False)
    parser.add_argument("--port02c-smoke", action="store_true")
    parser.add_argument("--release-root")
    parser.add_argument("--trusted-manifest-sha256")
    return parser.parse_args(argv)


def resolve_resources(args):
    if args.release_root is not None or args.trusted_manifest_sha256 is not None:
        if args.release_root is None or args.trusted_manifest_sha256 is None:
            raise DesktopLaunchError("installed launch requires an explicit trusted release")
        identity = verify_installed_release(args.release_root, args.trusted_manifest_sha256)
        return ResourceResolver.for_installed(identity)
    if getattr(sys, "frozen", False):
        # Existing PORT-02C hosted smoke supplies this out-of-band hash through
        # GITHUB_ENV. Never trust a hash read from the installed tree itself.
        if args.port02c_smoke and os.environ.get("MANIFEST_SHA"):
            root = Path(sys.executable).resolve().parents[2]
            identity = verify_installed_release(root, os.environ["MANIFEST_SHA"])
            return ResourceResolver.for_installed(identity)
        raise DesktopLaunchError("installed launch requires an explicit trusted release")
    identity = verify_development_checkout(Path(__file__).resolve().parent)
    return ResourceResolver.for_development(identity)


def resolve_writable_roots(resources) -> WritableRoots:
    """Bind OS user-data locations without consulting the current directory."""
    if type(resources) is not ResourceResolver:
        raise DesktopLaunchError("trusted local application paths could not be resolved")
    identity = resources.identity
    if type(identity) is InstalledReleaseIdentity:
        installed_release_root = identity.release_root
    elif type(identity) is DevelopmentCheckoutIdentity:
        installed_release_root = None
    else:
        raise DesktopLaunchError("trusted local application paths could not be resolved")
    try:
        return default_writable_roots(installed_release_root=installed_release_root)
    except ResourceResolutionError:
        # Never include environment-derived paths in a startup error.
        raise DesktopLaunchError("trusted local application paths could not be resolved") from None


def verify_health(observed, *, session, identity):
    expected = {"contract": "ATHENA_LOCAL_HEALTH_V1", "instance_id": session.instance_id,
                "challenge": session.challenge, "server_proof": session.proof("server"), "release": release_summary(identity),
                "runtime": {"platform": sys.platform, "python": platform.python_version()},
                "resources": "verified_snapshot", "provider_authority": False,
                "model_readiness": "unproven"}
    if observed != expected:
        raise DesktopLaunchError("local backend identity verification failed")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


class LocalBackend:
    def __init__(self, resources):
        self.resources = resources
        self.writable_roots = resolve_writable_roots(resources)
        self.session = LocalSession()
        self.app_repository = None
        self.listener = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        try:
            # Hold the actual socket through startup; never check then rebind.
            self.listener.bind(("127.0.0.1", 0))
            self.listener.listen(128)
            self.origin = f"http://127.0.0.1:{self.listener.getsockname()[1]}"
            # D3 app store: run the additive app schema once at startup and
            # capture truthful, immutable release provenance from the verified
            # identity. This store never grants run authority (POST /api/v1/runs
            # stays DURABLE_RUN_STORE_UNAVAILABLE).
            provenance = release_provenance(resources.identity, verified_at=_utc_now())
            self.app_repository = AppRepository.open(
                resources, self.writable_roots, release_id=provenance["release_id"])
            self.app_repository.record_release_manifest(**provenance)
            preview_store = DurablePreviewStore(
                self.app_repository, release_id=provenance["release_id"])
            preview_admission_service = AthenaPreviewAdmissionService(
                resources, preview_store=preview_store)
            app = create_app(release_identity=resources.identity, resource_resolver=resources,
                             writable_roots=self.writable_roots,
                             local_session=self.session,
                             capability_service=AthenaCapabilityService(
                                 resources, preview_admission_service=preview_admission_service),
                             preview_admission_service=preview_admission_service,
                             read_service=AthenaReadService.unavailable(),
                             origin=self.origin)
            self.server = uvicorn.Server(uvicorn.Config(app, log_level="critical", access_log=False))
            self.thread = threading.Thread(target=self.server.run, kwargs={"sockets": [self.listener]})
        except Exception:
            if self.app_repository is not None:
                self.app_repository.close()
            self.listener.close()
            self.session.invalidate()
            raise DesktopLaunchError("trusted local backend could not be constructed") from None

    def start(self):
        self.thread.start()
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                raise DesktopLaunchError("local backend redirect rejected")

        opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())
        headers = {"X-Athena-Handshake": self.session.proof("client"), "X-Athena-Instance": self.session.instance_id,
                   "X-Athena-Challenge": self.session.challenge}
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            if not self.thread.is_alive():
                raise DesktopLaunchError("local backend did not start")
            try:
                request = urllib.request.Request(self.origin + "/api/v1/health", headers=headers)
                with opener.open(request, timeout=.5) as response:
                    if response.status != 200 or response.geturl() != request.full_url:
                        raise DesktopLaunchError("local backend response was not trusted")
                    payload = response.read(16385)
                    if len(payload) > 16384:
                        raise DesktopLaunchError("local backend response exceeded its contract")
                    observed = json.loads(payload)
                verify_health(observed, session=self.session, identity=self.resources.identity)
                return
            except (OSError, TimeoutError):
                time.sleep(.05)
        raise DesktopLaunchError("local backend verification timed out")

    def close(self):
        self.session.invalidate()
        self.server.should_exit = True
        if self.thread.is_alive():
            self.thread.join(timeout=10)
        self.listener.close()
        if self.app_repository is not None:
            self.app_repository.close()
        if self.thread.is_alive():
            raise DesktopLaunchError("local backend did not stop")


def bootstrap_script(*, origin, session):
    # The check and delivery occur in one JS task in the actual document.
    # No native credential-return callback can resolve in a later navigation.
    payload = {"credential": session.credential(), "instance_id": session.instance_id,
               "challenge": session.challenge}
    return ("(()=>{if(location.origin!==" + json.dumps(origin) +
            "||location.pathname!=='/'||typeof window.athenaBootstrap!=='function')return;"
            "window.athenaBootstrap(" + json.dumps(payload) + ");})()")


def main(argv=None):
    backend = None
    try:
        args = parse_args(argv)
        backend = LocalBackend(resolve_resources(args))
        backend.start()  # Exact identity verification precedes native UI creation.
        if args.port02c_smoke:
            return 0
        import webview
        window = webview.create_window("ATHENA Research Preview", url=backend.origin + "/",
                                       js_api=None, width=1100, height=750)
        delivered = False
        lock = threading.Lock()

        def loaded():
            nonlocal delivered
            with lock:
                if delivered:
                    return
                delivered = True
                try:
                    window.run_js(bootstrap_script(origin=backend.origin, session=backend.session))
                except Exception:
                    backend.session.invalidate()
                    backend.server.should_exit = True
                    window.destroy()

        window.events.loaded += loaded
        webview.start(private_mode=True, debug=False, http_server=False)
        return 0
    except Exception:
        # Never print native exception text, paths, request headers or credentials.
        print("ATHENA local launch failed closed.", file=sys.stderr)
        return 1
    finally:
        if backend is not None:
            try:
                backend.close()
            except DesktopLaunchError:
                print("ATHENA local shutdown failed closed.", file=sys.stderr)
                return 1


if __name__ == "__main__":
    raise SystemExit(main())
