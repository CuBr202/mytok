# First-time setup: existing server files, new Git repository

This walkthrough assumes a new **private GitHub repository named `mytok`**.
Replace `YOUR_GITHUB_USERNAME`, `YOUR_NAME`, and `YOUR_EMAIL` before running
commands. GitLab or another Git host also works if you replace the repository URL.
Use Git 2.28+ and Python 3.9+. Run each stage on the machine indicated, in order.
If a command fails, resolve that failure before continuing to the next command.

The first small upload goes from Windows to GitHub so the server can obtain
the helper through Git. The server then uploads code and the dataset manifest.
The 51 GB of data stays on the server.

## 1. Create an empty repository on GitHub

Create `mytok`, select **Private**, and leave README, .gitignore, and license
initialization disabled. Its HTTPS URL will be:

```text
https://github.com/YOUR_GITHUB_USERNAME/mytok.git
```

Authenticate on both machines when Git requests it. Windows may open a browser
through its credential manager. If HTTPS Git prompts for a password in the
server terminal, enter a GitHub personal access token. A fine-grained token
should select this repository and grant Contents read/write permission.
Enter the token at the password prompt, rather than putting it in the URL.

## 2. Windows PowerShell: publish the helper first

The new local code repository will be a separate folder inside the LiteToken
workspace. This stage expects that the destination `mytok` folder does not exist.

```powershell
Set-Location 'C:\Users\28013\Desktop\research\LiteToken'
New-Item -ItemType Directory -Path '.\mytok' -ErrorAction Stop
Copy-Item -LiteralPath '.\transfer-tools' -Destination '.\mytok\transfer-tools' -Recurse
Set-Location '.\mytok'

git init -b main
git config user.name "YOUR_NAME"
git config user.email "YOUR_EMAIL"
git add transfer-tools/
git commit -m "Add dataset shadow helper"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/mytok.git
git push -u origin main
```

These identity settings apply only to this repository. The first commit contains
the helper and its documentation. Keep this local repository for step 6.

## 3. Server Bash: connect the existing directory

In the server terminal:

```bash
cd /home/yikesun/mytok
git --version
python3 --version
git init -b main
git config user.name "YOUR_NAME"
git config user.email "YOUR_EMAIL"
git remote add origin https://github.com/YOUR_GITHUB_USERNAME/mytok.git
git fetch origin
git checkout -b main --track origin/main
```

This fetches and checks out the helper commit inside the populated directory.
Existing code and data remain untracked at this point. The checkout refuses to
overwrite conflicting untracked files; if it reports a conflict, inspect those
specific paths before proceeding. Do not add a force option.

Confirm the helper arrived:

```bash
python3 transfer-tools/dataset_shadow.py --help
```

## 4. Server: exclude data before staging the project

Append the following to `.gitignore`. This preserves any rules already present.
The directory choices assume they contain generated data, as suggested by your
disk-usage listing. If any contains source code you need, adjust its rule first.

```bash
cat >> .gitignore <<'EOF'

# Generated datasets and intermediates
/c4/full_data/
/c4/errored_dataset/
/c4/errored_dataset_old/
/c4/generated/
/c4/entropy_old/
/c4/tmp_freq/
/c4/tmp_counters/

# Local shadow marker
/.dataset-shadow-local

# Python environments and caches
__pycache__/
*.py[cod]
.venv/
.ipynb_checkpoints/
EOF
```

`history/` is 8.8 GB and `c4/results/` is 620 MB, so decide what they contain
before staging them. If a whole directory is disposable generated output, add
`/history/` or `/c4/results/` to `.gitignore`. If it contains historical code,
configs, or useful small summaries, ignore only its data subdirectories/files.
Do not exclude all of `c4/`, because it may contain the active source code.
Keep credentials out of the tracked source as well.

The following **read-only** check reports new non-ignored files that would enter
the next `git add .`. It reads file metadata, not dataset contents:

```bash
python3 - <<'PY'
import os
import stat
import subprocess
from collections import defaultdict

raw = subprocess.check_output([
    'git', 'ls-files', '--others', '--exclude-standard', '-z'
])
rows = []
totals = defaultdict(int)
for entry in raw.split(b'\0'):
    if not entry:
        continue
    name = os.fsdecode(entry)
    info = os.lstat(name)
    if stat.S_ISREG(info.st_mode):
        rows.append((info.st_size, name))
        totals[name.split('/')[0]] += info.st_size

print(f'New non-ignored files: {len(rows):,}')
print(f'Total logical size: {sum(size for size, _ in rows) / 1024**2:,.1f} MiB')
print('\nTotals by top-level path:')
for name, size in sorted(totals.items(), key=lambda item: item[1], reverse=True):
    print(f'{size / 1024**2:12,.1f} MiB  {name!r}')
print('\nLargest 30 files:')
for size, name in sorted(rows, reverse=True)[:30]:
    print(f'{size / 1024**2:12,.1f} MiB  {name!r}')
PY
```

If datasets or multi-GB output are still included, add their ignore rules and
rerun the check. It sums all candidate files, so it also detects bulk data split
across many small files. Files ignored by the server's global Git config also
need shared `.gitignore` rules if local materialization is to recognize them.

## 5. Server: export the manifest, commit, and upload

After completing the ignore rules:

```bash
python3 transfer-tools/dataset_shadow.py export --scope c4 --scope history
```

This inventories ignored, untracked files under those two directories. It does
not automatically decide which files should be ignored. For additional data
directories, add more `--scope` arguments. The resulting
`dataset-manifest.jsonl` is tracked, and must stay outside ignored directories.

Create a small tracked note for local development:

```bash
cat >> DATASETS.md <<'EOF'

Real datasets and full experiments live at /home/yikesun/mytok on the server.
dataset-manifest.jsonl records ignored remote paths and their actual byte sizes.
In a local clone these files may be 0-byte placeholders. Do not interpret those
placeholders as corrupt data, parse them as datasets, or regenerate them.
Use the manifest to understand paths; run full data-dependent jobs on the server.
Use separately labeled small fixtures for local tests.
EOF
```

Now stage the selected source files, small results, and manifest:

```bash
git add .
git diff --cached --stat
git diff --cached --name-only
```

Review this list before committing. If a data file was accidentally staged,
remove it from staging without deleting it, then add its ignore rule:

```bash
git restore --staged -- path/to/accidentally_staged_file
```

After correcting ignore rules, rerun `export` and `git add .` so the manifest
includes newly excluded data. Then commit and push:

```bash
git commit -m "Import research code and remote dataset inventory"
git push
```

Only tracked content is uploaded. The existing real data stays in place.

## 6. Windows PowerShell: pull the code and create placeholders

Return to the local repository created in step 2. There is no need to clone again.

```powershell
Set-Location 'C:\Users\28013\Desktop\research\LiteToken\mytok'
git pull --ff-only
```

Use Python 3.9+. The following executable was verified on your current machine
and avoids an older `python` executable elsewhere on PATH:

```powershell
$shadowPython = 'C:\Users\28013\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe'
& $shadowPython --version
& $shadowPython transfer-tools/dataset_shadow.py materialize --dry-run
& $shadowPython transfer-tools/dataset_shadow.py materialize
git status --short
```

The helper creates missing empty files and their parent directories. It does not
truncate existing local files. The last command should show no changes from the
placeholders, because both they and the marker remain ignored.

Point your coding assistant at `DATASETS.md` and `dataset-manifest.jsonl` when
working on the code. Ordinary file searches may skip ignored paths; the manifest
provides the tracked inventory. Empty files cannot supply data schemas, values,
or runnable full experiments.

## 7. Normal synchronization

Pull before starting work on a machine. Keep tracked changes committed before
switching to the other machine; ignored real datasets do not need committing.

When editing code on Windows:

```powershell
git pull --ff-only
# Edit code, then stage the intended changes.
git add -u
# For new source files, also use: git add relative/path/to/new_file.py
git diff --cached --stat
git commit -m "Describe the code change"
git push
```

On the server, pull that code and run experiments:

```bash
cd /home/yikesun/mytok
git pull --ff-only
# Run your experiment commands here.
```

After the server data changes, refresh its inventory:

```bash
python3 transfer-tools/dataset_shadow.py export --scope c4 --scope history
git add dataset-manifest.jsonl
# Also stage any intended code changes or selected small result summaries.
git diff --cached --stat
git commit -m "Update dataset inventory"
git push
```

Back on Windows, pull and create any newly missing placeholders:

```powershell
git pull --ff-only
& $shadowPython transfer-tools/dataset_shadow.py materialize
```

If using a new PowerShell terminal, define `$shadowPython` again as in step 6.
If Git reports nothing to commit, skip that commit. If `--ff-only` fails because
both machines made separate commits, reconcile those commits before continuing;
do not force a push to bypass the divergence.

Run **export on the server** and **materialize locally**. Removed remote paths
are removed from the next manifest, but old local placeholders are not deleted
automatically. The latest manifest is authoritative. Symlinks remain
inventory-only; Windows-incompatible names cause materialization to stop before
creating files. With very large file counts, use the manifest alone to avoid the
filesystem metadata cost of millions of empty files.

## References

- [GitHub: importing existing code](https://docs.github.com/en/migrations/importing-source-code/using-the-command-line-to-import-source-code/adding-locally-hosted-code-to-github)
- [GitHub: HTTPS authentication](https://docs.github.com/en/get-started/git-basics/about-remote-repositories)
- [GitHub: personal access tokens](https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/managing-your-personal-access-tokens)
- [Git: shared ignore rules](https://git-scm.com/docs/gitignore)
