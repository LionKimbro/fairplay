# Fair Play: Python Package API

## Scope

This document describes the planned public interface after:

```python
import fairplay
```

It is an API specification for callers, not an implementation plan. Every writing operation owns a separate context dictionary so that worker threads cannot overwrite one another's intended targets or claim bookkeeping.

Except for `setup()`, every public Fair Play call requires setup to have completed. Calling one before setup raises an explicit setup-required error; it does not silently create a session identity.

## Process-wide data dictionary

The package exposes one stable, process-wide dictionary:

```python
fairplay.process
```

Its values are established when Fair Play initializes and are normally left alone. They are ordinary dictionary values rather than forcibly locked values: a caller could edit them, but doing so during execution is discouraged because all active contexts rely on the same process-wide meaning.

The initial keys are:

| Key | Logical type and initial value | Meaning |
|---|---|---|
| `session_guid` | UUID `str`; generated once at Fair Play initialization | Identifies this running Fair Play participant. Claims from this same session are not competitors. |
| `contention_window_seconds` | positive `int` or `float`; `5` | The required quiet observation period after claims are published. This is the protocol constant `n`. |

## Setup

```python
result = fairplay.setup()
```

`setup()` initializes the process-wide Fair Play identity. It assigns `fairplay.process["session_guid"]` a freshly generated UUID version 4 string in lowercase hyphenated form, for example:

```text
3f32d8e4-cb71-4c3e-a3cf-05e111dfd0ef
```

`setup()` is idempotent: after a session GUID has been established, later ordinary calls leave it unchanged. Replacing a process session GUID while claims from that session may still exist would make the process fail to recognize its own claims, so a new identity belongs to a new process lifetime rather than a routine re-setup. It returns the standard result dictionary described below, with a `process` key containing the current `fairplay.process` dictionary.

Call `setup()` before `new_context()` or any operation that creates or inspects claims.

## Global configuration dictionary

The package exposes one mutable program-default dictionary:

```python
fairplay.config
```

The calling program sets this dictionary before creating contexts. `new_context()` copies it into the new context; subsequent changes to `fairplay.config` do not alter an operation already in progress. The owner of a newly created context may adjust that context's `config` dictionary before beginning its claim operation, which permits thread-specific behavior without changing other contexts.

The initial keys are:

| Key | Logical type and default value | Meaning |
|---|---|---|
| `minimum_reup_seconds` | positive `int` or `float`; `1` | The minimum remaining lease time required to perform a re-up. Below this threshold, re-up is refused and the caller has `NO_LEASE`. |
| `auto_retry_max_attempts` | non-negative `int`; `5` | Maximum retries for a transient inspection uncertainty when the caller supplies `"auto-retry"`. `0` means no retries after the first failed inspection. |
| `auto_retry_wait_interval_ms` | non-negative `int`; `100` | Delay, in milliseconds, between automatic retries of an unreadable, incomplete, or temporarily uninterpretable claim file. |
| `block_timeout_seconds` | positive `int` or `float`, or `None`; `10` | Total time a `"block"` call may wait before returning `OK`, another decisive status, or `TIMEOUT`. `None` means no timeout. |

An invalid configuration value is a caller error and must be rejected before an operation begins. Durations are numeric seconds except for keys explicitly ending in `_ms`.

## Contexts

```python
ctxt = fairplay.new_context()
```

`new_context()` returns a context dictionary. It contains a snapshot of the mutable Fair Play configuration plus room for operation-local state. The context copies the program-wide session GUID from `fairplay.process`, but does not create a new session GUID for every context.

Contexts are owned by one operation at a time. They are suitable for passing to a worker that performs a particular claim-and-write task. Multiple contexts from the same running program share the same session GUID while retaining independent intended claims and published-claim IDs.

### Context dictionary schema

The following keys are maintained by the package. Callers pass the context as the first argument, but should not mutate its operation-state keys directly.

| Key | Logical type and initial value | Meaning |
|---|---|---|
| `config` | `dict`; copy of `fairplay.config` | Per-operation configuration snapshot. Its owner may adjust it before beginning the claim operation. Its values have the meanings defined above and do not include stable process data. |
| `session_guid` | UUID `str`; copied from `fairplay.process["session_guid"]` | Identifies the participant session. Claims from this same session are not competitors. |
| `operation_guid` | UUID `str`; newly generated by `new_context()` | Identifies this one operation context for local bookkeeping and safe cleanup. It is distinct from the program-wide session GUID and from every claim GUID. |
| `intended_claims` | `list`; initially `[]` | Normalized scope/path pairs supplied by `intend_claims()`. The list is the complete target set for the next claim attempt. |
| `published_claims` | `list`; initially `[]` | Records for the immutable claims published by this operation. Each record contains at least `claim_guid`, claim-file path, and expiry time. |
| `contention_window_ends_at` | comparable timestamp or `None`; initially `None` | The earliest time at which the operation may receive `OK` for its published claims, calculated using `fairplay.process["contention_window_seconds"]`. |
| `last_result` | Fair Play result symbol or `None`; initially `None` | The most recent result returned for this operation. It is diagnostic state, not continuing authority to write. |
| `last_competing_claims` | `list`; initially `[]` | Details of the competing claims found by the most recent scan, including conservatively rounded-up remaining seconds when available. |

`published_claims` is operation-local even when several contexts share a session GUID. This lets a failed or completed operation remove only the claim files it created, never another operation's claims from the same program.

## Intended claims

```python
result = fairplay.intend_claims(ctxt, list_of_claims)
```

Records the target set for this operation. Each entry is a scope/path pair:

```python
[
    (fairplay.FILE, "C:/lion/example/tasks.m1"),
    (fairplay.TREE, "C:/lion/github/new-checkout"),
]
```

`fairplay.FILE`, `fairplay.DIRECTORY`, and `fairplay.TREE` have the string values `"FILE"`, `"DIRECTORY"`, and `"TREE"`.

An empty list is valid and simply records no intended targets. Duplicate targets are also valid. Fair Play does not try to simplify, reject, or manage the caller's intention list.

Calling `intend_claims()` after this context has published claims is allowed. It replaces the context's intention slot for the next claim operation but does not automatically release, alter, or otherwise manage claims already published by the context. This permits callers to keep separate sets of claims alive when they have a legitimate reason to do so.

## Cleanup

```python
result = fairplay.cleanup(ctxt)
```

Deletes expired immutable claim files as a maintenance pass. Cleanup is not part of the time-sensitive authorization path: normal scans ignore expired claims whether or not cleanup has yet run.

Cleanup skips a claim file it cannot read. It does not retry unreadable files and does not treat them as permission to write; normal claim-inspection rules still apply when a later authorization check encounters one. Its result reports diagnostic counts, including `files_seen`, `valid_claim_files`, `expired_claim_files`, `files_removed`, `unreadable_files`, `invalid_claim_files`, and `remove_failures`.

## Creating claims

```python
result = fairplay.make_claims(ctxt, lease_seconds, flags=None)
```

First scans for competing claims, then publishes immutable JSON claim files for
the context's intended targets when clear. `lease_seconds` is the requested
lease duration. A live competitor produces `COMPETING_CLAIM` without publishing
anything. The normal non-blocking result after successful publication is
`WAIT`, because the five-second contention window has not finished.

The caller must not write after `WAIT`. It must call `check_competitors()` after the required observation period and receive `OK` for the intended writing batch.

## Releasing claims

```python
result = fairplay.release_claims(ctxt)
```

Deletes only the claim files recorded in this context's `published_claims` list. It is the normal final action after a writing operation. It never deletes claims merely because they share the same session GUID.

The result reports `claims_considered`, `claims_released`, `claim_files_missing`, and `release_failures`. A missing claim file is reported rather than treated as an error: it may already have been removed by cleanup after expiry.

## Checking authorization

```python
result = fairplay.check_competitors(ctxt, expected_seconds, flags=None)
```

Checks the context's live claims against the registry. `expected_seconds` is a conservative, rounded-up upper estimate for the next batch of writing. `OK` means there is no competing live overlap and sufficient remaining lease time for that batch.

Callers perform a fresh check immediately before a substantial writing batch. A prior `OK` is not authority for later work.

Before the contention window ends, `check_competitors()` returns `WAIT` unless another condition already produces a different status, such as `RETRY`, `COMPETING_CLAIM`, or `NO_LEASE`.

## Result dictionaries

Action functions return complex dictionaries. `new_context()` is the one intentional exception: it returns its new context dictionary directly. Every action-result dictionary includes these keys:

| Key | Logical type | Meaning |
|---|---|---|
| `status` | Fair Play result symbol | The decision or completion status for this call. |
| `function` | `str` | The public function that produced this result, such as `"make_claims"`. |
| `timestamp` | comparable timestamp `str` | When the function completed its decision or operation. |
| `session_guid` | UUID `str` | The process session identity used by this call. |
| `operation_guid` | UUID `str` or `None` | The context operation identity; `None` only for a process-level result such as `setup()`. |
| `own_claims` | `list` | Summaries of the context's relevant published claims, including claim GUID, claim-file path, and expiry, when applicable. |
| `remaining_seconds` | non-negative `int` or `None` | Conservatively rounded-up remaining seconds on the relevant own lease. `None` when no own lease is relevant. |
| `competing_claims` | `list` | Details of live competing claims found by the scan. Each entry contains `claim_file`, `claim` (the entire parsed JSON object), and `remaining_seconds` (conservatively rounded up). The structure of `claim` is defined in the JSON claim-file-format specification. |
| `retry` | `dict` | Inspection-retry diagnostics: `auto_retry_attempts`, `max_attempts`, and `will_retry`. |
| `diagnostics` | `list` | Human-readable diagnostic strings, warnings, or implementation-specific structured diagnostic records. |

Function-specific result keys are:

| Function | Key | Logical type | Meaning |
|---|---|---|---|
| `setup()` | `process` | `dict` | Snapshot of the current `fairplay.process` dictionary. |
| `intend_claims()` | `intended_claims` | `list` | The normalized scope/path list now stored in the context. |
| `cleanup()` | `files_seen` | non-negative `int` | Claim-registry files examined by cleanup. |
| `cleanup()` | `valid_claim_files` | non-negative `int` | Files cleanup could read and recognize as valid claim documents. |
| `cleanup()` | `expired_claim_files` | non-negative `int` | Valid claim files whose lease had expired when cleanup examined them. |
| `cleanup()` | `files_removed` | non-negative `int` | Expired claim files successfully deleted. |
| `cleanup()` | `unreadable_files` | non-negative `int` | Files cleanup could not read and therefore skipped. |
| `cleanup()` | `invalid_claim_files` | non-negative `int` | Readable files that did not provide sufficient valid claim information and were skipped. |
| `cleanup()` | `remove_failures` | `list` | Records describing attempted expired-claim deletions that did not succeed. |
| `make_claims()` | `lease_seconds` | positive `int` or `float` | Lease duration requested for the newly published claims. |
| `make_claims()` | `contention_window_ends_at` | comparable timestamp or `None` | Earliest time at which this published claim set can receive `OK`. |
| `make_claims()` | `claims_created` | `list` | Summaries of claim files successfully published by this call. |
| `make_claims()` | `claims_auto_withdrawn` | `list` | Summaries of claims created by this call and withdrawn after a failed blocked acquisition. |
| `make_claims()` | `auto_withdraw_missing` | `list` | Attempted claim files already absent while auto-withdrawing. |
| `make_claims()` | `auto_withdraw_failures` | `list` | Claim-file removal failures encountered while auto-withdrawing. |
| `check_competitors()` | `expected_seconds` | non-negative `int` | Conservative, rounded-up writing duration supplied by the caller for this authorization check. |
| `check_competitors()` | `contention_window_ends_at` | comparable timestamp or `None` | The relevant claim set's current observation-window end time. |
| `check_competitors()` | `reup_performed` | `bool` | Whether this call successfully published replacement claims and removed its prior claims. |
| `check_competitors()` | `replacement_claims_created` | `list` | Summaries of replacement claim files published by a successful re-up. |
| `check_competitors()` | `prior_claims_removed` | `list` | Summaries of original claim files removed after a successful re-up. |
| `release_claims()` | `claims_considered` | non-negative `int` | This context's published claims considered for release. |
| `release_claims()` | `claims_released` | `list` | Summaries of claim files successfully removed. |
| `release_claims()` | `claim_files_missing` | `list` | Claims whose files were already absent when release was attempted. |
| `release_claims()` | `release_failures` | `list` | Records describing releases that could not be completed. |

The result reports facts about the completed call; it does not impose a state machine or restrict the caller's later choices. Any status other than `OK` is simply not authority to write.

## Result symbols

The `status` key uses these symbolic values:

- `fairplay.WAIT`: claims were published, but the observation window has not completed.
- `fairplay.OK`: the operation is authorized for the stated writing batch.
- `fairplay.COMPETING_CLAIM`: another session has a live overlapping claim.
- `fairplay.RETRY`: a temporary inspection uncertainty prevented a reliable result.
- `fairplay.NO_LEASE`: the operation lacks a relevant live claim, including when fewer than one second remains.
- `fairplay.NOT_ENOUGH_TIME`: the operation has a live claim but lacks the requested writing runway.
- `fairplay.TIMEOUT`: a configured blocking period ended before the call could produce authorization or another decisive status.

Exact machine-clock comparisons remain authoritative; the remaining-seconds values in a result are intentionally rounded up for display and diagnostics.

## Flags

Flags are supplied as `None` or a list of strings. The currently defined flags are:

- `"block"`, accepted by `make_claims()`: the call never returns `WAIT`. It waits through the remaining contention window before returning a resolved status.
- `"auto-withdraw"`, accepted by `make_claims()` only with `"block"`: if blocked acquisition ends without `OK`, removes only claims created by that `make_claims()` call. Claims that predated the call remain published.
- `"re-up"`, accepted by `check_competitors()`: when the only problem is insufficient runway and at least one second remains, it creates replacement immutable claims and removes the prior claims after successful replacement publication.
- `"auto-retry"`, accepted by inspection/check operations: it retries transient unreadable or incomplete claim files using the configured retry policy.

For `make_claims()`, the initial scan reports a live competitor before publishing a claim. With `"block"`, a successful publication waits through the contention window rather than returning `WAIT`; a competitor or other non-`WAIT` condition is reported as soon as it is determined. A caller that wants blocking indefinitely sets `block_timeout_seconds` to `None`.

## Typical non-blocking use

```python
fairplay.setup()
ctxt = fairplay.new_context()
fairplay.intend_claims(ctxt, [(fairplay.FILE, "C:/lion/example/tasks.m1")])

result = fairplay.make_claims(ctxt, 60)
if result["status"] == fairplay.WAIT:
    # Wait for the contention window, then check immediately before writing.
    result = fairplay.check_competitors(ctxt, expected_seconds=10)

if result["status"] == fairplay.OK:
    try:
        # Write only the intended target(s).
        pass
    finally:
        fairplay.release_claims(ctxt)
```

The protocol requirement remains that successful operations remove their own claims when finished.
