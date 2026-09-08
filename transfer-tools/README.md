# Git-only dataset shadows for mytok

Starting with an untracked server folder? Follow [SETUP.md](SETUP.md) for the
complete Git-only bootstrap, first upload, Windows setup, and daily sync commands.

Real code travels through Git. Large datasets stay Git-ignored on both machines.
The server exports a tracked `dataset-manifest.jsonl` containing relative paths,
real byte sizes, and modification times. A local clone creates missing empty
files at those paths. No dataset contents are downloaded or read by this tool.

Python 3.9+ and Git are required. There are no Python package dependencies.

## Initial setup on the server

Copy this `transfer-tools` directory into `/home/yikesun/mytok` (pasting the
script through a terminal is enough if Git is your only file-transfer option).
Use an existing Git repository there, or initialize one with `git init`.

Append the applicable rules from `mytok.gitignore.example` to the repository's
`.gitignore`. Review the contents first. Do not exclude all of `c4/`: it may
contain the active source code. Inspect `history/` and `c4/results/` separately
so historical code and useful small summaries are not excluded accidentally.
Add `/.dataset-shadow-local` to `.gitignore` even if you customize all other rules.

The helper inventories **only ignored, untracked files** in the selected scopes.
Previously tracked large files are not made untracked by adding an ignore rule.
The helper does not modify the Git index or remove previously committed data.

From the server repository root:

```sh
cd /home/yikesun/mytok
python3 transfer-tools/dataset_shadow.py export --scope c4 --scope history
git add .gitignore dataset-manifest.jsonl transfer-tools/
```

Stage your actual source files and selected small results as well, inspect the
staged files, then commit and push to your existing Git remote. The helper does
not create a remote or perform commits or pushes for you.

Each manifest record is one line, for example (illustrative filename and size):

```json
{"path": "c4/full_data/counter/en/shard-0001.pkl", "kind": "file", "size_bytes": 987654321, "mtime_ns": 1788825600000000000}
```

The first line identifies the format and source root. File sizes are logical
byte sizes, so totals can differ from disk-usage output such as `du`.

## Create local shadows

Clone/pull the code repository on the local computer first. From its root:

```sh
python transfer-tools/dataset_shadow.py materialize --dry-run
python transfer-tools/dataset_shadow.py materialize
```

This recreates parent directories and missing 0-byte files. Existing files,
including real data or local test fixtures, are never overwritten, truncated,
or deleted. The files must remain ignored in the local clone. The helper refuses
tracked/non-ignored paths, directory traversal, symlink parents, Windows
junctions, and destination paths that collide on Windows.

Symlinks are recorded in the manifest but are not followed or recreated.
Standalone empty directories are not inventoried; parent directories of files
are recreated. Filenames that cannot be represented on Windows cause a clear
error before materialization; the manifest can still be used directly.

## Keep it updated

After server datasets change, rerun `export`, commit the updated manifest, and
push. Locally, pull and rerun `materialize`. Export only on the server; the local
marker prevents accidentally publishing placeholder sizes as real metadata.

This is an additive shadow view: a path removed from the manifest is not deleted
locally. The latest manifest is authoritative when deciding which files still
exist remotely. This avoids deleting real local files during synchronization.

## Explain the local environment

Keep a tracked dataset note alongside the code, with the following information:

> Real datasets and full experiments are on /home/yikesun/mytok on the server.
> dataset-manifest.jsonl is the inventory of the ignored remote data files.
> In the local clone, these paths may contain 0-byte placeholders. Their remote
> sizes are recorded as size_bytes. An empty local placeholder is not evidence
> of a broken dataset. Use the manifest to understand paths; do not parse or
> regenerate placeholder files. Dataset-dependent experiments run remotely.
> Local tests should use separate, explicitly labeled small fixtures.

Point the coding assistant to this note and the manifest when starting work.
The tracked inventory is still useful if ordinary searches skip ignored files.
For Parquet/Arrow/JSONL data, also keep small schema descriptions and a few
representative records when appropriate: empty files reveal names, not contents.

For extremely large file counts, skip materialization and use just the manifest.
Zero-byte files still consume filesystem metadata, and placeholders do not make
dataset-dependent code runnable locally.
