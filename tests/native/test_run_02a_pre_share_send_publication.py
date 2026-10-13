"""Native filesystem qualification of retained exact HTTP evidence publication."""
import hashlib

from database.app_migration_evidence import publish, contained


def test_share_response_unicode_immutable_publication(tmp_path):
    root = tmp_path / "athena-ünicode-share"
    root.mkdir()
    raw = b'{"bizCode":10000,"data":{"shareCode":"ABC123"}}\r\n'
    locator = "share-create-evidence/" + hashlib.sha256(raw).hexdigest() + ".json"
    target = publish(root, locator, raw)
    assert contained(root, locator).read_bytes() == raw
    assert publish(root, locator, raw) == target
    try:
        publish(root, locator, b"contradictory")
    except ValueError:
        pass
    else:
        raise AssertionError("retained evidence was overwritten")
    assert target.read_bytes() == raw
