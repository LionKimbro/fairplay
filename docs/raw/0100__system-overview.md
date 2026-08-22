# Fair Play: System Overview

## Purpose

Fair Play is a cooperative concurrency protocol, mediated by small, human-readable JSON files on a personal computer. It lets independently written programs share responsibility for arbitrary filesystem files (and folders and trees) without requiring a central database to become the mandatory gateway to that data.

The arbitrary filesystem files are untouched by Fair Play, as are the directories that host them. Coordination occurs in a specially demarcated folder containing temporary coordination metadata, so that cooperating programs can make their intentions visible, avoid accidental simultaneous writes, and wait when another program is already working on an overlapping target.

Fair Play is not primarily a file-locking system. It is a convention that preserves composability: a small tool can responsibly operate on the part of the filesystem it understands without joining a monolithic application or database.

## Architecture at a glance

Fair Play uses a shared machine-local folder that holds temporary JSON claim files. A claim names its owner session, the files or directories it intends to cover, and its expiry time. Programs scan that shared claim folder before writing. They publish their own claims, allow a short contention window for competing claims to become visible, then proceed only when no other live session has an overlapping claim.

The claim folder is runtime coordination state, not part of the enduring domain data. Its exact machine-root location and filesystem shape are defined in the filesystem description.

## Intended participants

The primary participants are automatic programs and worker tasks that write files. A later core client, Manual Checkout, will let the desktop user deliberately lease files or directory trees through the same underlying claim model.

Manual Checkout is planned as both a command-line tool and a Tkinter application. The Tkinter form will show a countdown, provide audible warnings near expiry, and offer controls such as release and re-up. The command-line form will provide equivalent lease operations without the graphical countdown and audible warnings.

## Core idea

Fair Play has one social rule that all participants must honor:

> Do not write to a target covered by another live Fair Play claim.

The protocol is advisory in the operating-system sense: it does not forcibly lock files or punish a program that ignores it. But it is mandatory for Fair Play participants. A program that writes through a competing claim violates the system's assumptions and can cause the system to fail.

## Document map

- The assumptions and boundaries document says what Fair Play promises and what it deliberately does not promise.
- The claim process protocol defines the timing and lifecycle rules.
- The filesystem description defines where claims live and how targets are compared.
- The JSON claim-file format defines the transport document that participants publish and read.
- The Python package API defines the callable interface exposed after `import fairplay`.
- The Manual Checkout document records the future human-facing client.
