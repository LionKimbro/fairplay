# Fair Play: Assumptions and Boundaries

## Operating environment

Fair Play is designed first for one personal computer, with a small number of cooperative programs, mostly reads, and low write contention. The normal case is that a writer finds no competing claim and proceeds after the protocol's short observation window.

It is designed for ordinary trusted civilian computing: a mundane personal system under ordinary household security assumptions. It is not designed as a hardened or adversarial service. The system may use normal access controls, but it does not attempt to be crowbar-safe, Byzantine-fault tolerant, or a security boundary.

The machine's comparable clock is the authority for every timing signal used by Fair Play. The initial contention-window constant, `n`, is five seconds.

## Required participant behavior

Every Fair Play participant is expected to meet these conditions:

1. It remains responsive enough to observe and react within `n` seconds.
2. Before writing, it publishes claims for every target it intends to write.
3. It waits through the contention window and performs a thorough scan before it writes.
4. It writes an expiry time into every claim.
5. It writes only targets that its live claims cover.
6. It deletes its own claims when its work is complete.
7. If delayed, expired, uncertain, or faced with a competing claim, it does not write until it has completed the protocol again.
8. It may remove an expired immutable claim during cleanup.

Readers decide for themselves whether a live claim makes a read unsafe or undesirable. Writers do not have that discretion: another live overlapping claim means do not write.

## What Fair Play provides

Under these assumptions, Fair Play makes concurrent writing rare, visible, and recoverable. It gives programs a shared, inspectable way to announce intent; gives other programs a clear reason to defer; and lets abandoned claims eventually stop blocking work.

It is well suited to human-scale filesystem data, specialized background tools, derived indexes and caches, repair tasks, and work that can wait or retry when contention appears.

## What Fair Play does not provide

Fair Play is not an operating-system lock, access-control mechanism, database transaction manager, or distributed-consensus protocol. It does not make a buggy or malicious writer obey. It does not by itself make a multi-file update all-or-nothing after a crash. It does not guarantee safety for high-frequency contention, strict uniqueness constraints, financial/accounting invariants, or irreversible mutations whose partial completion cannot be repaired.

Those needs call for stronger machinery such as SQLite, another transactional database, journaling, or an explicitly designed service.

## Synchronization and other machines

The design case is one machine. A synchronized claims folder might sometimes permit multi-machine use when synchronization is reliably faster than the contention window, but that is not a guarantee or a primary design target.

Manual Checkout is a core planned feature for deliberate human work across Git and similar synchronization boundaries. It will use Fair Play claims, but synchronization workflow and shared lease authority are separate concerns from the local protocol.
