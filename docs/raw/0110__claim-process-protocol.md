# Fair Play: Claim Process Protocol

## Terms

- A **session** is one running Fair Play participant identity, represented by a random session GUID generated when that program initializes.
- A **claim** is an immutable JSON document with its own random claim GUID.
- A **target** is a file, directory, or directory tree named by a claim.
- A **live claim** is one whose expiry time has not passed according to the machine clock.
- A **competitor** is a live claim from a different session whose target overlaps a target the caller intends to write.
- The **contention window** is `n = 5` seconds.

Claims from the caller's own session do not count as competitors. This permits one program session to coordinate several related worker operations without treating itself as an outside writer.

## Normal acquisition

Before beginning a writing batch, a caller records its intended targets in its operation context and publishes its claims. Each claim has a finite lease duration chosen by the caller.

After publishing, the caller waits for the full five-second contention window. It then scans the claim registry and proceeds only if all of these are true:

1. Its own relevant claim remains live.
2. No live claim from another session overlaps any intended target.
3. Its remaining lease time is at least the conservative, rounded-up duration estimated for the upcoming writing batch.

The final scan is required immediately before the batch begins. A previous clear scan is never authority to write later.

## Result meanings

The protocol uses symbolic outcomes rather than assuming that every check authorizes work:

- `WAIT`: the caller's claim exists, but the contention window has not completed.
- `OK`: the caller has a live claim, no competing live overlap, and enough remaining time for the requested batch.
- `COMPETING_CLAIM`: another session holds a live overlapping claim.
- `RETRY`: a temporary inspection failure prevents a reliable decision, such as a claim document being incompletely written.
- `NO_LEASE`: the caller has no relevant live claim, including when less than one second remains.
- `NOT_ENOUGH_TIME`: the caller has a live claim, but not enough time remains for the stated batch.

When a competing claim is reported, its remaining time should be supplied to the caller as a conservatively rounded-up number of seconds for display and logging. Permission decisions continue to use the exact machine clock.

## Writing

Once a caller receives `OK`, it may write only the targets covered by its intended claims, and only for the duration it just checked. Before another substantial batch, it calls the competitor check again with a new conservative estimate.

If a caller is paused, delayed, loses its lease, encounters a competing claim, or cannot make a reliable decision, it stops and does not write. It must recover by using the claim process again.

## Re-up

Claims are immutable once published. A caller never edits the expiry of an existing claim.

If an operation needs more time while its current claims remain live, it may request a re-up during a competitor check. Re-up is permitted only when at least one second remains on the existing claim. The caller publishes replacement immutable claim files first and removes the original claim files only after replacement publication succeeds. The replacement claims use fresh claim GUIDs but the same session GUID.

Because the old claims still protect the targets while the replacement claims are published, re-up does not require another five-second contention window. A competing caller must always rescan before writing and therefore sees the replacement claims when the original claims expire.

If fewer than one second remains, re-up is not permitted and the result is `NO_LEASE`. The caller must begin a fresh acquisition attempt.

## Cleanup

Cleanup is intentionally separate from the time-sensitive scan-and-write path. Expired claims are ignored for normal conflict decisions whether or not their files have yet been removed.

Any participant may periodically delete expired claim files. This is safe because published claims are immutable and never renewed in place. Cleanup should not delay a caller's normal scan or writing attempt.

## Why the protocol works in its intended setting

If two cooperative callers begin at almost the same time, each publishes its own claim before it is allowed to write. During the five-second window, each sees the other's claim at the final scan. Neither receives `OK`, so neither writes through the collision.

The protocol relies on the stated assumptions: participants respond within the window, make a fresh final scan, honor live competing claims, and abandon authority when their own lease expires. It is cooperation, not a substitute for transactional storage or hostile-environment locking.
