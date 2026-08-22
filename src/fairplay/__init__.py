"""Fair Play cooperative filesystem-write coordination.

Call :func:`setup` once per process, then use one context from
:func:`new_context` for each independent writing operation.
"""

from __future__ import annotations

import json
import math
import os
import random
import tempfile
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
RETRY = "RETRY"
NO_LEASE = "NO_LEASE"
NOT_ENOUGH_TIME = "NOT_ENOUGH_TIME"
TIMEOUT = "TIMEOUT"


process = {
    "session_guid": None,
    "contention_window_seconds": 5,
}

config = {
    "minimum_reup_seconds": 1,
    "auto_retry_max_attempts": 5,
    "auto_retry_wait_interval_ms": 100,
    "retry_max_attempts": 5,
    "retry_wait_interval_ms": 1000,
    "retry_jitter_ms": 250,
    "block_timeout_seconds": 10,
}

g = {
    "registry_path": None,
}


class FairPlaySetupRequiredError(RuntimeError):
    """Raised when a Fair Play operation is used before setup()."""


class FairPlayConfigurationError(ValueError):
    """Raised when a caller supplies an invalid Fair Play configuration."""


def setup():
    """Initialize the stable process session identity."""
    if process["session_guid"] is None:
        process["session_guid"] = str(uuid.uuid4())
    return {
        "status": OK,
        "function": "setup",
        "timestamp": _format_time(_now()),
        "session_guid": process["session_guid"],
        "operation_guid": None,
        "own_claims": [],
        "remaining_seconds": None,
        "competing_claims": [],
        "retry": _retry_details(None),
        "diagnostics": [],
        "process": dict(process),
    }


def new_context():
    """Create one independent operation context from the current defaults."""
    _require_setup()
    _validate_config(config)
    return {
        "config": dict(config),
        "session_guid": process["session_guid"],
        "operation_guid": str(uuid.uuid4()),
        "intended_claims": [],
        "published_claims": [],
        "contention_window_ends_at": None,
        "last_result": None,
        "last_competing_claims": [],
        "result": None,
        "block_started_at": None,
        "acquisition_retry_count": 0,
    }


def intend_claims(ctxt, list_of_claims):
    """Record normalized scope/path targets for this operation's next attempt."""
    _require_context(ctxt)
    targets = [_normalize_target(claim) for claim in list_of_claims]
    ctxt["intended_claims"] = targets
    _prepare_result(ctxt, "intend_claims")
    _set_status(ctxt, OK)
    _update_result(ctxt, {"intended_claims": list(targets)})
    return _pop_result(ctxt)


def cleanup(ctxt):
    """Remove expired, readable immutable claim files without delaying a scan."""
    _require_context(ctxt)
    counts = {
        "files_seen": 0,
        "valid_claim_files": 0,
        "expired_claim_files": 0,
        "files_removed": 0,
        "unreadable_files": 0,
        "invalid_claim_files": 0,
        "remove_failures": [],
    }
    registry = _get_registry()
    for claim_path in registry.glob("*.json"):
        counts["files_seen"] += 1
        try:
            claim = _read_claim(claim_path)
        except (OSError, ValueError, json.JSONDecodeError):
            counts["unreadable_files"] += 1
            continue
        expires_at = _claim_expiry(claim)
        if expires_at is None:
            counts["invalid_claim_files"] += 1
            continue
        counts["valid_claim_files"] += 1
        if expires_at > _now():
            continue
        counts["expired_claim_files"] += 1
        try:
            claim_path.unlink()
            counts["files_removed"] += 1
        except OSError as error:
            counts["remove_failures"].append({"claim_file": str(claim_path), "error": str(error)})
    _prepare_result(ctxt, "cleanup")
    _set_status(ctxt, OK)
    _update_result(ctxt, counts)
    return _pop_result(ctxt)


def make_claims(ctxt, lease_seconds, flags=None):
    """Publish immutable claims, optionally waiting and retrying for authorization."""
    _require_context(ctxt)
    _validate_config(ctxt["config"])
    _validate_number(lease_seconds, "lease_seconds")
    flags = _validate_flags(flags, {"block", "retry", "auto-retry"})
    if not ctxt["intended_claims"]:
        _prepare_result(ctxt, "make_claims")
        _set_status(ctxt, NO_LEASE)
        _update_result(ctxt, {
            "lease_seconds": lease_seconds,
            "contention_window_ends_at": None,
            "claims_created": [],
            "claims_removed_before_retry": [],
            "diagnostics": ["No intended targets were recorded for this operation."],
        })
        return _pop_result(ctxt)
    ctxt["acquisition_retry_count"] = 0
    ctxt["block_started_at"] = time.monotonic() if "block" in flags else None
    removed_before_retry = []

    while True:
        claims_created = _publish_claims(ctxt, lease_seconds)
        _prepare_result(ctxt, "make_claims")
        _set_status(ctxt, WAIT)
        _update_result(ctxt, {
            "lease_seconds": lease_seconds,
            "contention_window_ends_at": ctxt["contention_window_ends_at"],
            "claims_created": claims_created,
            "claims_removed_before_retry": removed_before_retry,
            "retry": _retry_details(ctxt),
        })
        result = _pop_result(ctxt)
        if "block" not in flags:
            return result

        checked = _wait_and_check_for_claim_acquisition(ctxt, flags)
        checked["function"] = "make_claims"
        checked["lease_seconds"] = lease_seconds
        checked["claims_created"] = claims_created
        checked["claims_removed_before_retry"] = removed_before_retry
        if checked["status"] != COMPETING_CLAIM:
            return checked
        if not _may_retry_this_claim_acquisition(ctxt):
            return checked
        release = release_claims(ctxt)
        removed_before_retry.extend(release["claims_released"])
        ctxt["acquisition_retry_count"] += 1
        _sleep_for_acquisition_retry(ctxt)


def release_claims(ctxt):
    """Release only the immutable claim files published by this context."""
    _require_context(ctxt)
    released = []
    missing = []
    failures = []
    records = list(ctxt["published_claims"])
    retained = []
    for record in records:
        claim_path = Path(record["claim_file"])
        try:
            claim_path.unlink()
            released.append(dict(record))
        except FileNotFoundError:
            missing.append(dict(record))
        except OSError as error:
            retained.append(record)
            failures.append({"claim": dict(record), "error": str(error)})
    ctxt["published_claims"] = retained
    _prepare_result(ctxt, "release_claims")
    _set_status(ctxt, OK)
    _update_result(ctxt, {
        "claims_considered": len(records),
        "claims_released": released,
        "claim_files_missing": missing,
        "release_failures": failures,
    })
    return _pop_result(ctxt)


def check_competitors(ctxt, expected_seconds, flags=None):
    """Return whether this context may begin its next writing batch."""
    _require_context(ctxt)
    _validate_config(ctxt["config"])
    expected_seconds = _normalize_expected_seconds(expected_seconds)
    flags = _validate_flags(flags, {"block", "re-up", "auto-retry"})
    ctxt["block_started_at"] = time.monotonic() if "block" in flags else None
    ctxt["acquisition_retry_count"] = 0
    return _check_competitors(ctxt, expected_seconds, flags)


def _check_competitors(ctxt, expected_seconds, flags=None):
    flags = flags or []
    while True:
        result = _check_once(ctxt, expected_seconds, flags)
        result["retry"] = _retry_details(ctxt)
        if result["status"] == RETRY and "auto-retry" in flags:
            attempts = 0
            while result["status"] == RETRY and attempts < ctxt["config"]["auto_retry_max_attempts"]:
                attempts += 1
                _sleep_ms(ctxt["config"]["auto_retry_wait_interval_ms"])
                result = _check_once(ctxt, expected_seconds, flags)
            result["retry"] = _retry_details(ctxt, attempts)
        if result["status"] != WAIT or "block" not in flags:
            return result
        if _is_block_expired(ctxt):
            _prepare_result(ctxt, "check_competitors")
            _set_status(ctxt, TIMEOUT)
            _update_result(ctxt, {"expected_seconds": expected_seconds})
            return _pop_result(ctxt)
        _sleep_until_contention_window_or_timeout(ctxt)


def _check_once(ctxt, expected_seconds, flags=None):
    flags = flags or []
    own_claims = _read_claims(ctxt)
    remaining = _lease_time(own_claims)
    if not own_claims or remaining is None or remaining < ctxt["config"]["minimum_reup_seconds"]:
        _prepare_result(ctxt, "check_competitors")
        _set_status(ctxt, NO_LEASE)
        _update_result(ctxt, {"expected_seconds": expected_seconds})
        return _pop_result(ctxt)
    scan = _scan_for_competing_claims(ctxt)
    if scan["status"] == RETRY:
        _prepare_result(ctxt, "check_competitors")
        _set_status(ctxt, RETRY)
        _update_result(ctxt, {"expected_seconds": expected_seconds, "diagnostics": scan["diagnostics"]})
        return _pop_result(ctxt)
    if scan["competing_claims"]:
        ctxt["last_competing_claims"] = scan["competing_claims"]
        _prepare_result(ctxt, "check_competitors")
        _set_status(ctxt, COMPETING_CLAIM)
        _update_result(ctxt, {"expected_seconds": expected_seconds, "competing_claims": scan["competing_claims"]})
        return _pop_result(ctxt)
    ends_at = _parse_time(ctxt["contention_window_ends_at"]) if ctxt["contention_window_ends_at"] else None
    if ends_at is not None and _now() < ends_at:
        _prepare_result(ctxt, "check_competitors")
        _set_status(ctxt, WAIT)
        _update_result(ctxt, {"expected_seconds": expected_seconds})
        return _pop_result(ctxt)
    if remaining < expected_seconds:
        if "re-up" in flags:
            reup = _publish_replacement_claims_now(ctxt)
            if reup is not None:
                replacement_remaining = _lease_time(_read_claims(ctxt))
                if replacement_remaining is not None and replacement_remaining >= expected_seconds:
                    _prepare_result(ctxt, "check_competitors")
                    _set_status(ctxt, OK)
                    _update_result(ctxt, {"expected_seconds": expected_seconds, **reup})
                    return _pop_result(ctxt)
                _prepare_result(ctxt, "check_competitors")
                _set_status(ctxt, NOT_ENOUGH_TIME)
                _update_result(ctxt, {"expected_seconds": expected_seconds, **reup})
                return _pop_result(ctxt)
        _prepare_result(ctxt, "check_competitors")
        _set_status(ctxt, NOT_ENOUGH_TIME)
        _update_result(ctxt, {"expected_seconds": expected_seconds})
        return _pop_result(ctxt)
    _prepare_result(ctxt, "check_competitors")
    _set_status(ctxt, OK)
    _update_result(ctxt, {"expected_seconds": expected_seconds})
    return _pop_result(ctxt)


def _publish_claims(ctxt, lease_seconds):
    now = _now()
    expires_at = now.timestamp() + lease_seconds
    claim_guid = str(uuid.uuid4())
    claim = {
        "format_version": 1,
        "claim_guid": claim_guid,
        "session_guid": ctxt["session_guid"],
        "created_at": _format_time(now),
        "expires_at": _format_time(datetime.fromtimestamp(expires_at, timezone.utc)),
        "targets": [{"scope": scope, "path": path} for scope, path in ctxt["intended_claims"]],
    }
    claim_path = _get_registry() / f"{claim_guid}.json"
    _write_immutable_claim(claim_path, claim)
    record = {
        "claim_guid": claim_guid,
        "claim_file": str(claim_path),
        "expires_at": claim["expires_at"],
        "targets": list(ctxt["intended_claims"]),
        "lease_seconds": lease_seconds,
    }
    ctxt["published_claims"].append(record)
    ctxt["contention_window_ends_at"] = _format_time(
        datetime.fromtimestamp(now.timestamp() + process["contention_window_seconds"], timezone.utc)
    )
    return [dict(record)]


def _publish_replacement_claims_now(ctxt):
    records = _read_claims(ctxt)
    if not records:
        return None
    lease_seconds = max(record.get("lease_seconds", 0) for record in records)
    if lease_seconds <= 0:
        return None
    prior_records = list(ctxt["published_claims"])
    replacements = _publish_claims(ctxt, lease_seconds)
    ctxt["contention_window_ends_at"] = None
    prior_paths = {record["claim_file"] for record in prior_records}
    prior_removed = []
    retained = []
    for record in ctxt["published_claims"]:
        if record["claim_file"] not in prior_paths:
            retained.append(record)
            continue
        try:
            Path(record["claim_file"]).unlink()
            prior_removed.append(dict(record))
        except OSError:
            retained.append(record)
    ctxt["published_claims"] = retained
    return {
        "reup_performed": True,
        "replacement_claims_created": replacements,
        "prior_claims_removed": prior_removed,
    }


def _scan_for_competing_claims(ctxt):
    competitors = []
    diagnostics = []
    for claim_path in _get_registry().glob("*.json"):
        try:
            claim = _read_claim(claim_path)
            expiry = _claim_expiry(claim)
            targets = _claim_targets(claim)
            session_guid = claim.get("session_guid")
            if expiry is None or targets is None or not isinstance(session_guid, str) or not session_guid:
                raise ValueError("claim lacks required comparison information")
        except (OSError, ValueError, json.JSONDecodeError) as error:
            diagnostics.append(f"Could not reliably inspect {claim_path.name}: {error}")
            return {"status": RETRY, "competing_claims": [], "diagnostics": diagnostics}
        if expiry <= _now() or session_guid == ctxt["session_guid"]:
            continue
        if _has_overlap(ctxt["intended_claims"], targets):
            competitors.append({
                "claim_file": str(claim_path),
                "claim": claim,
                "remaining_seconds": _remaining_lease(expiry),
            })
    return {"status": OK, "competing_claims": competitors, "diagnostics": diagnostics}


def _read_claims(ctxt):
    records = []
    for record in ctxt["published_claims"]:
        try:
            claim = _read_claim(Path(record["claim_file"]))
            expiry = _claim_expiry(claim)
            targets = _claim_targets(claim)
        except (OSError, ValueError, json.JSONDecodeError):
            continue
        if claim.get("session_guid") != ctxt["session_guid"] or expiry is None or targets is None:
            continue
        if expiry > _now() and _has_overlap(ctxt["intended_claims"], targets):
            copied = dict(record)
            copied["expires_at"] = _format_time(expiry)
            records.append(copied)
    return records


def _read_claim(claim_path):
    claim = json.loads(claim_path.read_text(encoding="utf-8"))
    if not isinstance(claim, dict):
        raise ValueError("claim document is not an object")
    claim_guid = claim.get("claim_guid")
    if not isinstance(claim_guid, str) or claim_path.stem != claim_guid:
        raise ValueError("claim filename does not match claim_guid")
    return claim


def _claim_expiry(claim):
    value = claim.get("expires_at")
    if not isinstance(value, str):
        return None
    try:
        return _parse_time(value)
    except ValueError:
        return None


def _claim_targets(claim):
    raw_targets = claim.get("targets")
    if not isinstance(raw_targets, list) or not raw_targets:
        return None
    try:
        return [_normalize_target((target["scope"], target["path"])) for target in raw_targets]
    except (KeyError, TypeError, ValueError):
        return None


def _normalize_target(claim):
    if not isinstance(claim, (tuple, list)) or len(claim) != 2:
        raise ValueError("each claim must be a (scope, path) pair")
    scope, path = claim
    if scope not in {FILE, DIRECTORY, TREE}:
        raise ValueError(f"unknown claim scope: {scope!r}")
    if not isinstance(path, (str, os.PathLike)) or not os.fspath(path):
        raise ValueError("claim path must be a non-empty path string")
    normalized = os.path.normpath(os.path.abspath(os.fspath(path)))
    if os.name == "nt":
        normalized = os.path.normcase(normalized)
    return scope, normalized


def _has_overlap(left, right):
    return any(_is_one_target_overlapping_another(first, second) for first in left for second in right)


def _is_one_target_overlapping_another(left, right):
    left_scope, left_path = left
    right_scope, right_path = right
    if left_scope == TREE and right_scope == TREE:
        return _is_below(left_path, right_path) or _is_below(right_path, left_path)
    if left_scope == TREE:
        return _is_below(right_path, left_path)
    if right_scope == TREE:
        return _is_below(left_path, right_path)
    return left_path == right_path


def _is_below(path, root):
    try:
        return os.path.commonpath((path, root)) == root
    except ValueError:
        return False


def _write_immutable_claim(claim_path, claim):
    payload = json.dumps(claim, indent=2, sort_keys=True) + "\n"
    descriptor, temporary_name = tempfile.mkstemp(prefix=".fairplay-", suffix=".tmp", dir=claim_path.parent, text=True)
    try:
        with os.fdopen(descriptor, "w", encoding="utf-8", newline="\n") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary_name, claim_path)
    except BaseException:
        try:
            os.unlink(temporary_name)
        except FileNotFoundError:
            pass
        raise


def _get_registry():
    if g["registry_path"] is None:
        g["registry_path"] = Path(machineroot.get("fair-play")) / "claims"
    registry = Path(g["registry_path"])
    registry.mkdir(parents=True, exist_ok=True)
    return registry


def _wait_and_check_for_claim_acquisition(ctxt, flags=None):
    check_flags = [flag for flag in flags or [] if flag in {"block", "auto-retry"}]
    return _check_competitors(ctxt, 0, check_flags)


def _may_retry_this_claim_acquisition(ctxt):
    limit = ctxt["config"]["retry_max_attempts"]
    if _is_block_expired(ctxt):
        return False
    return limit is None or ctxt["acquisition_retry_count"] < limit


def _sleep_for_acquisition_retry(ctxt):
    delay = ctxt["config"]["retry_wait_interval_ms"] + random.uniform(0, ctxt["config"]["retry_jitter_ms"])
    _sleep_ms(delay)


def _sleep_until_contention_window_or_timeout(ctxt):
    ends_at = _parse_time(ctxt["contention_window_ends_at"])
    seconds = max(0.0, (ends_at - _now()).total_seconds())
    timeout = ctxt["config"]["block_timeout_seconds"]
    if timeout is not None:
        seconds = min(seconds, max(0.0, timeout - (time.monotonic() - ctxt["block_started_at"])))
    time.sleep(seconds)


def _is_block_expired(ctxt):
    timeout = ctxt["config"]["block_timeout_seconds"]
    return timeout is not None and time.monotonic() - ctxt["block_started_at"] >= timeout


def _lease_time(records):
    if not records:
        return None
    return min(max(0.0, (_parse_time(record["expires_at"]) - _now()).total_seconds()) for record in records)


def _remaining_lease(expires_at):
    return max(0, math.ceil((expires_at - _now()).total_seconds()))


def _prepare_result(ctxt, function):
    ctxt["result"] = {
        "status": None,
        "function": function,
        "timestamp": None,
        "session_guid": process["session_guid"],
        "operation_guid": ctxt["operation_guid"],
        "own_claims": [],
        "remaining_seconds": None,
        "competing_claims": [],
        "retry": _retry_details(ctxt),
        "diagnostics": [],
    }


def _set_status(ctxt, status):
    if ctxt["result"] is None:
        raise RuntimeError("a result must be prepared before its status is set")
    ctxt["result"]["status"] = status
    ctxt["last_result"] = status


def _update_result(ctxt, details):
    if ctxt["result"] is None:
        raise RuntimeError("a result must be prepared before it is updated")
    ctxt["result"].update(details)


def _pop_result(ctxt):
    result = ctxt["result"]
    if result is None or result["status"] is None:
        raise RuntimeError("a result must be prepared and given a status before return")
    result["timestamp"] = _format_time(_now())
    result["own_claims"] = _own_claim_summaries(ctxt)
    result["remaining_seconds"] = _lease_time(_read_claims(ctxt))
    result["competing_claims"] = list(ctxt["last_competing_claims"])
    for claim in result["competing_claims"]:
        expiry = _claim_expiry(claim["claim"])
        if expiry is not None:
            claim["remaining_seconds"] = _remaining_lease(expiry)
    ctxt["result"] = None
    return result


def _own_claim_summaries(ctxt):
    if ctxt is None:
        return []
    return [
        {key: record[key] for key in ("claim_guid", "claim_file", "expires_at")}
        for record in _read_claims(ctxt)
    ]


def _retry_details(ctxt, auto_retries=0):
    return {
        "auto_retry_attempts": auto_retries,
        "acquisition_retry_attempts": ctxt["acquisition_retry_count"] if ctxt else 0,
        "max_attempts": ctxt["config"]["retry_max_attempts"] if ctxt else None,
        "will_retry": False,
    }


def _require_setup():
    if process["session_guid"] is None:
        raise FairPlaySetupRequiredError("fairplay.setup() must complete before this operation")


def _require_context(ctxt):
    _require_setup()
    required = {"config", "session_guid", "operation_guid", "intended_claims", "published_claims"}
    if not isinstance(ctxt, dict) or not required.issubset(ctxt):
        raise ValueError("ctxt must be a context returned by fairplay.new_context()")


def _validate_config(values):
    required = {
        "minimum_reup_seconds", "auto_retry_max_attempts", "auto_retry_wait_interval_ms",
        "retry_max_attempts", "retry_wait_interval_ms", "retry_jitter_ms", "block_timeout_seconds",
    }
    if not isinstance(values, dict) or set(values) != required:
        raise FairPlayConfigurationError("config must contain exactly the specified Fair Play keys")
    if _type_checks(values["minimum_reup_seconds"], ["!finite", "!<=0"]):
        raise FairPlayConfigurationError("minimum_reup_seconds must be positive")
    for name in ("retry_wait_interval_ms", "retry_jitter_ms"):
        _validate_nonnegative(values[name], name)
    for name in ("auto_retry_max_attempts", "auto_retry_wait_interval_ms"):
        if _type_checks(values[name], ["!int", "!<0"]):
            raise FairPlayConfigurationError(f"{name} must be a non-negative integer")
    if values["retry_max_attempts"] is not None and _type_checks(values["retry_max_attempts"], ["!int", "!<0"]):
        raise FairPlayConfigurationError("retry_max_attempts must be a non-negative integer or None")
    timeout = values["block_timeout_seconds"]
    if timeout is not None:
        _validate_number(timeout, "block_timeout_seconds")


def _validate_flags(flags, allowed):
    if flags is None:
        return []
    if not isinstance(flags, list) or any(not isinstance(flag, str) or flag not in allowed for flag in flags):
        raise ValueError(f"flags must be a list containing only: {', '.join(sorted(allowed))}")
    return list(flags)


def _validate_number(value, name):
    if _type_checks(value, ["!finite", "!<=0"]):
        raise ValueError(f"{name} must be a positive finite number")


def _validate_nonnegative(value, name):
    if _type_checks(value, ["!finite", "!<0"]):
        raise FairPlayConfigurationError(f"{name} must be a non-negative finite number")


def _type_checks(value, flags):
    failures = []
    for flag in flags:
        if flag == "!int" and (not isinstance(value, int) or isinstance(value, bool)):
            failures.append(flag)
        elif flag == "!float" and (not isinstance(value, float) or isinstance(value, bool)):
            failures.append(flag)
        elif flag == "!finite" and (
            not isinstance(value, (int, float)) or isinstance(value, bool) or not math.isfinite(value)
        ):
            failures.append(flag)
        elif flag.startswith("!<=") and isinstance(value, (int, float)) and value <= float(flag[3:]):
            failures.append(flag)
        elif flag.startswith("!<") and not flag.startswith("!<=") and isinstance(value, (int, float)) and value < float(flag[2:]):
            failures.append(flag)
        elif flag not in {"!int", "!float", "!finite"} and not flag.startswith("!<"):
            raise ValueError(f"unknown type check: {flag}")
    return failures


def _normalize_expected_seconds(value):
    _validate_nonnegative(value, "expected_seconds")
    return math.ceil(value)


def _now():
    return datetime.now(timezone.utc)


def _format_time(value):
    return value.isoformat(timespec="microseconds").replace("+00:00", "Z")


def _parse_time(value):
    parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    if parsed.tzinfo is None:
        raise ValueError("timestamp must include a timezone")
    return parsed.astimezone(timezone.utc)
