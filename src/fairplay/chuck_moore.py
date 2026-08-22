"""A deliberately bare Fair Play implementation sketch."""

import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import machineroot


FILE = "FILE"
DIRECTORY = "DIRECTORY"
TREE = "TREE"

WAIT = "WAIT"
OK = "OK"
COMPETING_CLAIM = "COMPETING_CLAIM"
NO_LEASE = "NO_LEASE"
NOT_ENOUGH_TIME = "NOT_ENOUGH_TIME"

process = {
    "session_guid": None,
    "registry_path": None,
    "contention_window_seconds": 5,
}


def setup():
    process["session_guid"] = str(uuid.uuid4())
    process["registry_path"] = Path(machineroot.get("fair-play")) / "claims"
    process["registry_path"].mkdir(parents=True, exist_ok=True)


def new_context():
    return {
        "session_guid": process["session_guid"],
        "intended_claims": [],
        "published_claims": [],
        "attempted_claims": [],
        "contention_window_ends_at": None,
    }


def intend_claims(ctxt, claims):
    ctxt["intended_claims"] = [(scope, _path(path)) for scope, path in claims]


def make_claims(ctxt, seconds, flags=None):
    flags = flags or []
    ctxt["attempted_claims"] = []
    if _find_competition(ctxt):
        return COMPETING_CLAIM
    now = _now()
    claim_guid = str(uuid.uuid4())
    expires_at = now.timestamp() + seconds
    claim = {
        "format_version": 1,
        "claim_guid": claim_guid,
        "session_guid": ctxt["session_guid"],
        "created_at": _time(now),
        "expires_at": _time(datetime.fromtimestamp(expires_at, timezone.utc)),
        "targets": [{"scope": scope, "path": path} for scope, path in ctxt["intended_claims"]],
    }
    claim_path = _registry() / f"{claim_guid}.json"
    claim_path.write_text(json.dumps(claim), encoding="utf-8")
    record = {"claim_file": str(claim_path), "expires_at": claim["expires_at"]}
    ctxt["published_claims"].append(record)
    ctxt["attempted_claims"].append(record)
    ctxt["contention_window_ends_at"] = now.timestamp() + process["contention_window_seconds"]
    if "block" not in flags:
        return WAIT
    time.sleep(process["contention_window_seconds"])
    status = check_competitors(ctxt, 0)
    if "auto-withdraw" in flags and status != OK:
        _withdraw_current_attempt_claims(ctxt)
    return status


def check_competitors(ctxt, seconds):
    own_claims = _read_current_claims(ctxt)
    if not own_claims:
        return NO_LEASE
    if _now().timestamp() < ctxt["contention_window_ends_at"]:
        return WAIT
    if min(_parse(claim["expires_at"]).timestamp() for claim in own_claims) - _now().timestamp() < seconds:
        return NOT_ENOUGH_TIME
    if _find_competition(ctxt):
        return COMPETING_CLAIM
    return OK


def release_claims(ctxt):
    for claim in ctxt["published_claims"]:
        Path(claim["claim_file"]).unlink(missing_ok=True)
    ctxt["published_claims"].clear()
    return OK


def _withdraw_current_attempt_claims(ctxt):
    records = list(ctxt["attempted_claims"])
    paths = {record["claim_file"] for record in records}
    for record in records:
        Path(record["claim_file"]).unlink(missing_ok=True)
    ctxt["published_claims"] = [record for record in ctxt["published_claims"] if record["claim_file"] not in paths]
    ctxt["attempted_claims"] = []


def cleanup():
    now = _now().timestamp()
    for claim_path in _registry().glob("*.json"):
        claim = _read_claim(claim_path)
        if _parse(claim["expires_at"]).timestamp() <= now:
            claim_path.unlink()
    return OK


def _read_current_claims(ctxt):
    claims = []
    now = _now().timestamp()
    for record in ctxt["published_claims"]:
        claim_path = Path(record["claim_file"])
        if claim_path.exists() and _parse(record["expires_at"]).timestamp() > now:
            claims.append(record)
    return claims


def _find_competition(ctxt):
    for claim_path in _registry().glob("*.json"):
        claim = _read_claim(claim_path)
        if claim["session_guid"] == ctxt["session_guid"]:
            continue
        if _parse(claim["expires_at"]).timestamp() <= _now().timestamp():
            continue
        for target in claim["targets"]:
            for intended in ctxt["intended_claims"]:
                if _is_one_target_overlapping_another((target["scope"], _path(target["path"])), intended):
                    return True
    return False


def _read_claim(claim_path):
    return json.loads(claim_path.read_text(encoding="utf-8"))


def _is_one_target_overlapping_another(left, right):
    left_scope, left_path = left
    right_scope, right_path = right
    if left_scope == TREE and right_scope == TREE:
        return _below(left_path, right_path) or _below(right_path, left_path)
    if left_scope == TREE:
        return _below(right_path, left_path)
    if right_scope == TREE:
        return _below(left_path, right_path)
    return left_path == right_path


def _below(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _registry():
    return process["registry_path"]


def _path(path):
    return os.path.normcase(os.path.normpath(os.path.abspath(path)))


def _now():
    return datetime.now(timezone.utc)


def _time(value):
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse(value):
    return datetime.fromisoformat(value.replace("Z", "+00:00"))
