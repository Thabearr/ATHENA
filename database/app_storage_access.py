"""Verified SQLite access shared by the D5 offline storage services."""
from __future__ import annotations

from contextlib import contextmanager

from database.app_migrations import (
    app_store_path,
    connect_app_store,
    expected_schema_structure,
    read_app_migrations,
    verify_app_schema,
)
from database.app_root_lock import app_root_lock
from runtime.resources import ResourceResolver, WritableRoots


@contextmanager
def app_store_connection(resources: ResourceResolver, roots: WritableRoots, *, write=False):
    """Yield one verified transactional connection while owning the root lock."""
    if type(resources) is not ResourceResolver or type(roots) is not WritableRoots:
        raise ValueError("verified resources and writable roots are required")
    migrations = read_app_migrations(resources)
    identities = [(version, digest) for version, _path, _raw, digest in migrations]
    with app_root_lock(roots.data_root):
        path = app_store_path(roots)
        connection = connect_app_store(path, readonly=not write,
                                       synchronous="FULL" if write else "NORMAL")
        try:
            connection.execute("BEGIN IMMEDIATE" if write else "BEGIN")
            verify_app_schema(connection, expected_structure=expected_schema_structure(migrations))
            recorded = connection.execute(
                "SELECT version, migration_sha256 FROM app_schema_migrations ORDER BY version"
            ).fetchall()
            if recorded != identities:
                raise ValueError("stored migration ledger differs from verified resources")
            yield connection
            connection.commit()
        except BaseException:
            connection.rollback()
            raise
        finally:
            connection.close()


__all__ = ["app_store_connection"]
