# Fair Play Python API

## What Fair Play does

Fair Play is a cooperative protocol for programs that write filesystem paths.
Before writing, a program publishes a short-lived claim. It then waits for the
contention window and writes only after a fresh check returns `OK`.

Fair Play is advisory. Every participating writer must honor its results.

```python
import fairplay
```

Use the main `fairplay` package for the supported API. The separate
`fairplay.chuck_moore` module is an implementation experiment, not the
consumer API.

## The normal flow

```python
fairplay.setup()

ctxt = fairplay.new_context()
fairplay.intend_claims(ctxt, [
    (fairplay.FILE, "C:/work/report.json"),
])

result = fairplay.make_claims(ctxt, 60, ["block", "auto-retry", "auto-withdraw"])
if result["status"] == fairplay.OK:
    try:
        # Write only C:/work/report.json here.
        pass
    finally:
        # Releases the successful claim. Failed acquisition was already withdrawn.
        fairplay.release_claims(ctxt)
```

Call `check_competitors()` immediately before each substantial writing batch.
An earlier `OK` is not permission for later work.

## Setup and process state

### `setup()`

```python
result = fairplay.setup()
```

Call this once before every other Fair Play operation. It is safe to call
again: the existing process session is retained.

Setup creates a process session GUID and resolves the MachineRoot key
`fair-play` once. The resulting claims directory is stored in:

```python
fairplay.process["registry_path"]
```

`fairplay.process` also contains:

| Key | Meaning |
|---|---|
| `session_guid` | Identity shared by all contexts in this process. Own claims never compete with one another. |
| `contention_window_seconds` | The post-publication observation period. Default: `5`. |
| `registry_path` | The fixed `claims/` directory chosen during setup. |

Do not change these values during an active process.

## Contexts

### `new_context()`

```python
ctxt = fairplay.new_context()
```

Create one context for each independent writing operation or worker. Contexts
share the process session but keep their intended targets and published claims
separate. Do not use one context concurrently from multiple workers.

Every public function other than `setup()` requires setup first. Otherwise it
raises `FairPlaySetupRequiredError`.

## Targets

Provide claims as `(scope, path)` pairs:

```python
[
    (fairplay.FILE, "C:/work/report.json"),
    (fairplay.DIRECTORY, "C:/work/inbox"),
    (fairplay.TREE, "C:/work/project"),
]
```

| Scope | Covers |
|---|---|
| `FILE` | Exactly that file path. |
| `DIRECTORY` | Exactly that directory, not descendants. |
| `TREE` | That directory and every descendant path. |

Paths are made absolute and normalized lexically. Windows comparisons are
case-insensitive; Linux comparisons are case-sensitive. Symlinks, junctions,
and other aliases are not resolved.

### `intend_claims(ctxt, claims)`

Stores the targets for the context's next claim attempt.

```python
fairplay.intend_claims(ctxt, [(fairplay.TREE, "C:/work/project")])
```

Changing intended targets does not release claims already published by the
context.

## Claim acquisition

### `make_claims(ctxt, lease_seconds, flags=None)`

First looks for a live competing claim. If one exists, it returns
`COMPETING_CLAIM` without publishing. Otherwise it publishes immutable claim
files for the intended targets.

```python
result = fairplay.make_claims(ctxt, 60)
```

Without flags, a successful publication returns `WAIT`. The caller must later
check before writing.

Supported flags:

| Flag | Meaning |
|---|---|
| `"block"` | Wait through the observation window rather than returning `WAIT`. |
| `"auto-withdraw"` | With `"block"`, withdraw only claims created by this call if acquisition ultimately fails. |
| `"auto-retry"` | Retry temporary claim-file inspection failures during the acquisition check. |

`"auto-withdraw"` leaves claims that existed before this `make_claims()` call
alone. `"auto-retry"` concerns only temporarily unsafe claim-file inspection.

### `check_competitors(ctxt, expected_seconds, flags=None)`

Performs the fresh authorization check for the next writing batch.

```python
result = fairplay.check_competitors(ctxt, 10)
```

`expected_seconds` is a conservative upper estimate for the work about to be
written. `OK` requires a live own claim, no live overlapping claim from a
different session, and enough lease time for that estimate.

Supported flags:

| Flag | Meaning |
|---|---|
| `"re-up"` | Replace a live but too-short claim with a fresh immutable claim. |
| `"auto-retry"` | Retry transient unreadable/incomplete claim-file inspection failures. |

Re-up is refused if too little lease time remains. It publishes replacements
before removing originals.

## Result statuses

Every action except `new_context()` returns a dictionary with `status`.

| Status | Meaning |
|---|---|
| `OK` | The requested writing batch is authorized. |
| `WAIT` | Claims exist, but the observation window is incomplete. Do not write. |
| `COMPETING_CLAIM` | Another session has a live overlapping claim. Do not write. |
| `RETRY` | A claim file could not be safely inspected. Do not write. |
| `NO_LEASE` | No relevant live own claim remains. Do not write. |
| `NOT_ENOUGH_TIME` | The claim is live but lacks runway for the estimated batch. Do not write. |
| `TIMEOUT` | A blocking operation reached its configured time limit. Do not write. |

Only `OK` authorizes writing, and only for the targets claimed by that context
and the batch duration just checked.

## Result dictionaries

All action results include:

| Key | Meaning |
|---|---|
| `status` | One of the symbols above. |
| `function` | Public operation that produced the result. |
| `timestamp` | UTC completion time. |
| `session_guid` / `operation_guid` | The process and operation identities. |
| `own_claims` | Relevant claims published by this context. |
| `remaining_seconds` | Rounded-up display value for the shortest relevant own lease. |
| `competing_claims` | Live overlaps found during the current scan. |
| `retry` | Retry counts and limits. |
| `diagnostics` | Human-readable warnings or details. |

Action-specific data is included when useful:

- `intend_claims()`: `intended_claims`
- `make_claims()`: `lease_seconds`, `contention_window_ends_at`,
  `claims_created`, and, when applicable,
  `claims_auto_withdrawn`, `auto_withdraw_missing`, `auto_withdraw_failures`
- `check_competitors()`: `expected_seconds`, and re-up information when used
- `release_claims()`: released, missing, and failed claim-file records
- `cleanup()`: file counts and removal failures
- `setup()`: a `process` snapshot

The result is a completed snapshot. Its time-related values describe return
time, not the start of the operation.

## Releasing and cleanup

### `release_claims(ctxt)`

Delete only the claim files published by this context.

```python
fairplay.release_claims(ctxt)
```

Call it in a `finally` block after writing. It does not delete same-session
claims created by another context.

### `cleanup(ctxt)`

Remove readable expired claim files as maintenance.

```python
fairplay.cleanup(ctxt)
```

Cleanup is never authorization. An unreadable claim file is skipped by cleanup
and remains a `RETRY` condition for a later authorization check.

## Configuration

Set defaults before creating contexts:

```python
fairplay.config["block_timeout_seconds"] = 30
```

Each new context copies the current configuration. You may adjust that
context's `config` before its operation begins without affecting other
contexts.

| Key | Default | Meaning |
|---|---:|---|
| `minimum_reup_seconds` | 1 | Minimum remaining time required to re-up. |
| `auto_retry_max_attempts` | 5 | Retries for temporary inspection uncertainty. |
| `auto_retry_wait_interval_ms` | 100 | Delay between automatic inspection retries. |
| `block_timeout_seconds` | 10 | Total blocking wait; `None` means no timeout. |

## Error handling

Fair Play raises exceptions for caller mistakes such as setup omission, invalid
configuration, invalid flags, invalid scopes, and invalid durations. Treat
those as programming errors. Treat a non-`OK` result as a normal protocol
decision: do not write, then wait, use `"auto-retry"` for temporary inspection
uncertainty, re-up, or report the conflict as appropriate.
