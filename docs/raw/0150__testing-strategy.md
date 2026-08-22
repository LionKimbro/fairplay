# Fair Play: Testing Strategy

## Purpose

Fair Play coordinates filesystem writes. Its tests must therefore prove both
ordinary success and safe refusal: a transient uncertainty, expired lease, or
live competing claim must never be mistaken for permission to write.

The package will use `pytest` for its test suite. Tests belong in `tests/` and
are run with:

```text
python -m pytest
```

The suite must run without a real user MachineRoot registry and must never use
the machine's real Fair Play claims directory.

## Test environment

Every test receives a fresh temporary directory. The test redirects Fair
Play's claim-registry location to a `claims/` directory below that temporary
directory. No test may create, inspect, modify, or clean up claims outside its
own temporary directory.

Each test also starts with a fresh Fair Play process state and default
configuration. This prevents one test's session GUID, configuration edits, or
published claims from influencing another test.

Time-dependent tests must not wait for real five-second contention windows.
They should replace Fair Play's clock and sleep boundaries with a controlled
test clock. The controlled clock supplies both comparable UTC timestamps and a
monotonic elapsed time, and advances when the tested code sleeps. This makes
contention, expiry, retry, timeout, and re-up tests immediate and repeatable.

## Test layers

### Package API tests

These tests use only public Fair Play functions and inspect returned result
dictionaries plus claim files in the temporary registry.

They cover:

- setup is idempotent and produces a lowercase UUID4 session GUID;
- every operation except `setup()` rejects use before setup;
- `new_context()` receives an independent configuration copy and operation
  GUID while sharing the process session GUID;
- intended targets are normalized according to the local lexical path policy;
- successful claim publication produces immutable JSON with the required
  fields and a filename matching its claim GUID;
- `make_claims()` returns `WAIT` before the contention window and no result
  other than `OK` is treated as write authority;
- `check_competitors()` returns `OK` only after the window, with a live own
  claim and enough requested runway;
- release removes only claims published by that exact context;
- cleanup removes readable expired claims, reports failures, and skips
  unreadable files without treating them as harmless.

### Claim-reading safety tests

Construct claim files directly in the temporary registry to test all reader
decisions. In particular, test valid claims with unknown extra fields and
newer format versions, because tolerant reading is required.

Test these conditions produce `RETRY`, never `OK`:

- invalid JSON or a partially written JSON document;
- a JSON value that is not an object;
- filename/`claim_guid` mismatch;
- absent or unusable session, expiry, or target information; and
- target records with an unknown scope or unusable path.

Also test that expired claims are ignored for authorization even before
cleanup removes them.

### Target-overlap matrix

Parameterized tests cover every scope pairing after path normalization:

| First target | Second target | Expected overlap |
|---|---|---|
| `FILE(a)` | `FILE(a)` | yes |
| `FILE(a)` | `FILE(b)` | no |
| `FILE(a)` | `DIRECTORY(a)` | yes |
| `FILE(child)` | `DIRECTORY(parent)` | no |
| `FILE(child)` | `TREE(parent)` | yes |
| `DIRECTORY(a)` | `DIRECTORY(a)` | yes |
| `DIRECTORY(child)` | `TREE(parent)` | yes |
| `TREE(a)` | `TREE(child)` | yes |
| `TREE(left)` | `TREE(right)` | no |

The matrix must additionally include `.` and `..` normalization and the local
case policy. Windows-specific assertions run only on Windows; Linux-specific
assertions run only on Linux.

### Contention and lease tests

Use two separate contexts with distinct session GUIDs to model participants.

- Two overlapping live claims from different sessions yield
  `COMPETING_CLAIM`, with a rounded-up positive remaining time.
- Same-session claims do not compete.
- Non-overlapping claims permit `OK` after the observation window.
- A claim with fewer than `minimum_reup_seconds` remaining yields `NO_LEASE`.
- A live claim with insufficient requested runway yields `NOT_ENOUGH_TIME`.
- `"block"` waits through the window under the controlled clock and ends in
  `OK`, a decisive failure, or `TIMEOUT` according to configuration.
- `"auto-retry"` retries unreadable inspection failures exactly up to its
  configured limit.
- A failed blocked acquisition using `"auto-withdraw"` removes only claims
  created by that call; previously published claims in the context remain.

### Re-up tests

Re-up is protocol-critical because it replaces immutable claims without a new
contention window.

Test that a permitted re-up:

- requires at least `minimum_reup_seconds` remaining;
- publishes replacement claims before removing originals;
- uses new claim GUIDs and preserves the session GUID;
- returns `OK` only when the replacement lease covers the requested batch;
- retains the original claim if replacement publication fails; and
- leaves no stale context bookkeeping after successful replacement.

### Result-register tests

For every public operation result, assert that:

- `ctxt["result"]` is `None` after the result is returned;
- the returned dictionary has the required common result fields;
- `timestamp`, `remaining_seconds`, and competing-claim countdowns describe
  the controlled clock at return time; and
- changing a returned dictionary does not recreate or mutate the cleared
  context result register.

`setup()` receives a separate process-level result test because it has no
operation context.

### Configuration and input validation tests

Parameterized tests reject every invalid configuration type, missing key, and
out-of-range value before an operation starts. Additional tests reject invalid
lease durations, expected durations, flags, target pairs, paths, and scopes.

Tests also verify that each context snapshots `fairplay.config`: later changes
to the global dictionary do not alter an already created context.

### Style-auditor tests

`check.py` is part of the development safety net. Test it with small temporary
Python modules that deliberately contain:

- a one-call internal function with a short name;
- a repeatedly called internal function with a long name;
- a public package function with a valid short name;
- predicate and callback prefix word-count cases;
- more than three arguments;
- a three-argument function without final `flags`; and
- valid and invalid `flags` annotations/defaults.

The test verifies both the exit status and the human-readable finding.

## Test file layout

```text
tests/
    conftest.py
    test_setup_and_contexts.py
    test_claim_files.py
    test_target_overlap.py
    test_competition_and_leases.py
    test_reup.py
    test_cleanup.py
    test_results.py
    test_configuration.py
    test_check_style_auditor.py
```

## Completion standard

Before a Fair Play change is considered complete:

1. The focused affected test file passes.
2. The full `python -m pytest` suite passes.
3. `python check.py` reports zero style problems.
4. New protocol behavior has a regression test, including the failure path
   when a mistaken `OK` could permit an unsafe write.

The suite is not a proof of cooperative correctness. It is the executable
record of the protocol decisions that must stay stable as the implementation
becomes clearer.
