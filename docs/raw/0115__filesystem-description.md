# Fair Play: Filesystem Description

## Claim registry location

Fair Play keeps its temporary coordination state in a shared, machine-local registry. The Machine-Root key is:

```text
fair-play
```

The claim registry is the `claims` subdirectory beneath that root:

```text
<machine-root fair-play location>/
    claims/
        <claim-guid>.json
        <claim-guid>.json
        ...
```

The registry is authoritative for Fair Play claims. Ordinary data directories do not need to contain claim files or markers. Peer-directory additions may be explored later, but they are not part of the initial claim protocol.

Machine-Root resolution details, including the supporting Python package and environment-variable behavior, are supplied to the implementer when that integration is needed.

## Claim files

Each published claim is one JSON file named with a newly generated random GUID:

```text
<guid>.json
```

The GUID naming scheme avoids relying on target-derived lock filenames and permits a single claim to cover multiple unrelated targets. The JSON format is defined separately in the JSON claim-file format document.

## Target scopes

Every intended target carries one of these scope symbols:

```text
FILE = "FILE"
DIRECTORY = "DIRECTORY"
TREE = "TREE"
```

- `FILE` covers exactly the named file.
- `DIRECTORY` covers exactly the named directory, not its descendants.
- `TREE` covers the named directory and every descendant path beneath it.

The exact public Python representation is a scope/path pair, such as `("FILE", "C:/lion/example/data.json")`.

## Path normalization

Fair Play compares normalized, absolute filesystem paths. The purpose of normalization is to ensure that two ordinary spellings of the same path are compared consistently before conflict identification.

The initial path policy is lexical and local:

1. Callers supply paths for the local machine.
2. Fair Play makes each path absolute and normalizes separators plus `.` and `..` components.
3. On Windows, comparison follows the local Windows case-insensitive path convention.
4. On Linux, comparison follows the local case-sensitive path convention.

The first version does not promise to identify distinct aliases created by symbolic links, junctions, reparse points, mounts, or other filesystem indirection. Callers that need Fair Play coordination must use one agreed normal path spelling for the same resource. This limitation is preferable to claiming a stronger canonicalization guarantee than the filesystem can safely provide for paths that may not yet exist.

## Conflict identification

Two claims conflict when any target from one claim overlaps any target from the other after normalization, and the claims belong to different session GUIDs.

The basic rules are:

- `FILE(path)` overlaps `FILE(path)` only when the paths are equal.
- `FILE(path)` overlaps `DIRECTORY(path)` only when the file path and directory path are the same filesystem object; it does not overlap a directory merely because the file is inside it.
- `FILE(path)` overlaps `TREE(directory)` when the file is the tree root or is beneath it.
- `DIRECTORY(path)` overlaps `DIRECTORY(path)` when the paths are equal.
- `DIRECTORY(path)` overlaps `TREE(directory)` when the directory is the tree root or is beneath it.
- `TREE(a)` overlaps `TREE(b)` when either tree root is the other root or an ancestor of the other.

For the normal practical case, a target's kind should match what it names: use `FILE` for a file and `DIRECTORY` or `TREE` for a directory. A participant cannot write through an overlap merely by narrowing or restating its own claim; any live different-session overlap prevents authorization.
