# Fair Play: Manual Checkout

## Status

Manual Checkout is a core planned Fair Play client. It is not the first implementation target, and this document is intentionally a design placeholder.

## Purpose

Manual Checkout lets a desktop user deliberately lease files or directory trees through the same Fair Play claim model used by automatic programs. It is intended especially for work that crosses synchronization boundaries, including Git-based workflows, where the user wants a clear checkout period before editing, committing, pushing, and releasing.

Manual Checkout does not alter the meaning of a Fair Play claim. It is a human-facing lifecycle around the same session identity, target scopes, claims, expiry, re-up, release, and conflict rules.

## Planned forms

### Command line

The command-line tool will let a user request a lease, inspect status, re-up, and release. It provides the operational capabilities without an on-screen countdown or audible warnings.

### Tkinter application

The Tkinter form will present the active checkout clearly, including:

- the checked-out target or targets;
- the current user/session identity as appropriate;
- a visible countdown until lease expiry;
- audible warnings as expiry approaches;
- a re-up control;
- a release-now control; and
- an expired state that tells the user not to continue writing until a new lease has been acquired.

## Future workflow questions

The later design should define the exact workflow for Git and other synchronization systems, including when to pull/fetch, when a claim must become visible to another machine, when to commit/push, and when release is allowed. Fair Play's local claim protocol remains single-machine by design; synchronization correctness is a separate layer to be specified for Manual Checkout.
