# Fair Play: JSON Claim-File Format

## Purpose

A Fair Play claim file is a small, immutable JSON document published in the shared claims registry. It tells other participants who holds the claim, what paths it covers, and when the claim stops being live.

## Required information

Every claim supplies the following semantic information:

- A format version.
- A random **claim GUID**, unique to this claim file.
- A random **session GUID**, generated once when the participant program initializes and shared by its contexts.
- A creation time from the machine-comparable clock.
- An expiry time from the same clock.
- One or more target records, each with a scope and path.

An optional short human-readable purpose may be included for inspection and diagnostics.

## Initial JSON shape

The initial format uses the following field names:

```json
{
  "format_version": 1,
  "claim_guid": "2d370d37-06f1-4f3d-b84f-e8db4cceee70",
  "session_guid": "f4978c83-4044-41b6-a2c9-f1b17b1075f8",
  "created_at": "2026-08-22T08:15:00Z",
  "expires_at": "2026-08-22T08:16:00Z",
  "targets": [
    {
      "scope": "FILE",
      "path": "C:/lion/example/tasks.m1"
    },
    {
      "scope": "TREE",
      "path": "C:/lion/github/new-checkout"
    }
  ],
  "purpose": "Update day files"
}
```

The filename is `<claim_guid>.json`. A participant should reject a discrepancy between the filename GUID and the JSON `claim_guid` as an inspection failure rather than silently assuming the document is harmless.

## Publication and immutability

The writer constructs the complete JSON document before publishing it to the claim file. Once published, a claim is immutable. Re-up creates a separate claim file with a fresh claim GUID; it never changes `expires_at` in the existing file.

Readers may encounter a file while it is being written. A JSON parse failure, a document that cannot provide the information needed for the requested comparison, or a filename/claim-GUID mismatch is a temporary uncertainty and leads to `RETRY` under the caller's configured retry policy. It never authorizes a write.

## Tolerant reading and format evolution

Readers should be liberal about harmless additions and newer versions. Unknown extra fields must not invalidate an otherwise understandable claim. A reader should extract and use the target, session identity, and expiry information it understands rather than rejecting a document merely because its `format_version` is newer.

However, liberal reading does not mean guessing. If the reader cannot determine enough information to decide whether the claim overlaps its requested targets and whether it is live, it cannot safely authorize writing while that uncertainty remains. It returns `RETRY` according to its configured policy.

## Time representation

Creation and expiry values must be machine-wide comparable timestamps. They are not process-relative elapsed timers, because different processes need to compare the same expiry moment. The display form above is UTC ISO 8601; the implementation may additionally preserve a more precise machine-readable representation if needed, provided all participants retain the same comparison semantics.
