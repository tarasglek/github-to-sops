# GitHub Integration Tests Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add real integration tests that exercise GitHub CLI identity, key import through the actual `github-to-sops` CLI, repository collaborator lookup, install-only supported-major SOPS release lookup, install-only SOPS release asset download/checksum verification, and block local pushes when the integration test fails.

**Architecture:** Add `tests/test_github_integration.py` with live tests that require authenticated `gh`, real network access, a GitHub-authenticated developer identity with public SSH keys, and a supported SOPS release platform. Add a hardcoded supported SOPS major version and a `get_latest_sops_version()` helper used only by `install()` so SOPS install uses the newest upstream release within the supported major version instead of a stale hardcoded exact version or an unsupported future major. Add a shared, testable SOPS release download helper that downloads the current supported SOPS binary and checksums into a temporary directory and verifies SHA256 without performing the privileged final install. The installer must use this same helper, and any Docker-based install/test flow must use this same path rather than duplicating download logic. Normal non-install commands (`import-keys`, `updatekeys`) must never discover, download, install, or upgrade SOPS. Refactor `main(argv=None)` so tests can exercise command dispatch directly without spawning a subprocess, while preserving normal CLI behavior when `argv` is omitted. Add a committed `.githooks/pre-push` hook that runs the integration tests with `uv run --with pytest`.

**Tech Stack:** Python standard library, `pytest` via `uv run --with pytest`, GitHub CLI (`gh`), git pre-push hook.

---

## Design

### Test policy

These are integration tests, not unit tests. They require real network, authenticated `gh`, a GitHub identity with public SSH keys, repository collaborator access, and a supported SOPS release platform. Missing prerequisites are test failures.

### Behaviors covered

1. Pull current GitHub username from `gh api user --jq .login`.
2. Fetch public SSH keys for that username through `fetch_github_ssh_keys()`.
3. Seed a `.sops.yaml` through the actual CLI using explicit `--github-users LOGIN` recipients.
4. Update that seeded `.sops.yaml` in place through the actual CLI using explicit `--github-users LOGIN` recipients.
5. Seed a `.sops.yaml` through the actual CLI using repository collaborators fetched from GitHub.
6. Update that seeded `.sops.yaml` in place through the actual CLI using repository collaborators fetched from GitHub.
7. Pull latest supported-major SOPS release tag through `gh release list --repo getsops/sops`.
8. Verify code helper returns the newest SOPS tag within the hardcoded supported major version.
9. Download the latest supported-major SOPS release binary and checksum file through `gh release download` into a temporary test directory only.
10. Verify the downloaded SOPS binary against the upstream checksum file without installing or upgrading the local SOPS binary.
11. Assert non-install CLI paths do not invoke SOPS version discovery or release download.
12. Exercise `main(argv=None)` testability without changing normal command-line behavior.
13. Block `git push` locally if these integration tests fail.

---

## Task 1: Add latest supported-major SOPS version helper

**Files:**
- Modify: `github_to_sops/__init__.py`

**Step 1: Write failing test first**

Create `tests/test_github_integration.py` with this initial test:

```python
import subprocess

import github_to_sops


def run_checked(args):
    return subprocess.run(args, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE, check=True)


def test_latest_sops_version_matches_newest_supported_major_gh_release():
    result = run_checked([
        "gh", "release", "list",
        "--repo", "getsops/sops",
        "--json", "tagName,isDraft,isPrerelease",
        "--jq", f"[.[] | select((.isDraft | not) and (.isPrerelease | not) and (.tagName | startswith(\"v{github_to_sops.SUPPORTED_SOPS_MAJOR}.\")))][0].tagName",
    ])
    expected = result.stdout.strip()

    assert expected.startswith(f"v{github_to_sops.SUPPORTED_SOPS_MAJOR}.")
    assert github_to_sops.get_latest_sops_version() == expected
```

**Step 2: Run and verify failure**

Run:

```bash
uv run --with pytest pytest -v tests/test_github_integration.py::test_latest_sops_version_matches_gh_release_view
```

Expected: fail with `AttributeError: module 'github_to_sops' has no attribute 'SUPPORTED_SOPS_MAJOR'` or `get_latest_sops_version` until the supported-major helper is implemented.

**Step 3: Implement helper**

Add to `github_to_sops/__init__.py` near the SOPS install helpers:

```python
SUPPORTED_SOPS_MAJOR = 3


def get_latest_sops_version() -> str:
    try:
        result = subprocess.run(
            [
                "gh", "release", "list",
                "--repo", "getsops/sops",
                "--json", "tagName,isDraft,isPrerelease",
                "--jq", f"[.[] | select((.isDraft | not) and (.isPrerelease | not) and (.tagName | startswith(\"v{SUPPORTED_SOPS_MAJOR}.\")))][0].tagName",
            ],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        print("GitHub CLI `gh` is required to discover the latest sops release. Install gh first.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Failed to discover latest sops release with gh: {e.stderr.strip()}", file=sys.stderr)
        sys.exit(1)

    version = result.stdout.strip()
    if not version.startswith(f"v{SUPPORTED_SOPS_MAJOR}."):
        print(f"Unexpected sops release tag for supported major {SUPPORTED_SOPS_MAJOR}: {version}", file=sys.stderr)
        sys.exit(1)
    return version
```

**Step 4: Update installer to use latest**

In `download_and_install_sops()`, replace:

```python
version = "v3.10.2"
```

with:

```python
version = get_latest_sops_version()
```

**Step 5: Run test and verify pass**

Run:

```bash
uv run --with pytest pytest -v tests/test_github_integration.py::test_latest_sops_version_matches_gh_release_view
```

Expected: pass.

---

## Task 2: Add GitHub identity and CLI seed/update integration tests

**Files:**
- Modify: `tests/test_github_integration.py`

**Step 1: Add test helpers, direct key-fetch test, and CLI seed/update tests**

Extend the file with helpers that run the real checkout CLI wrapper `./github-to-sops`, write temporary `.sops.yaml` files, and assert generated content contains `Generated by`, the GitHub-to-SOPS tag, SSH keys, and expected usernames.

Add tests for:

1. `test_current_gh_identity_has_fetchable_public_keys()`.
2. `test_cli_seeds_and_updates_sops_yaml_for_explicit_user()`.
3. `test_cli_seeds_and_updates_sops_yaml_for_repo_collaborators()`.

The explicit-user test must seed the file by redirecting CLI stdout to `.sops.yaml`, then run `--inplace-edit .sops.yaml` and verify the file still contains generated keys for the current login.

The repository-collaborator test must seed the file without `--github-users`, relying on the local checkout's GitHub remote and `gh api repos/OWNER/REPO/collaborators`, then run `--inplace-edit .sops.yaml` without `--github-users` and verify the file still contains generated SSH keys.

**Step 2: Run tests**

Run:

```bash
uv run --with pytest pytest -v tests/test_github_integration.py
```

Expected: all GitHub identity and CLI seed/update integration tests pass. `gh` must be installed/authenticated and the current GitHub user must have at least one public SSH key; missing prerequisites are test failures.

---

## Task 3: Add testable SOPS release download helper and integration test

**Files:**
- Modify: `github_to_sops/__init__.py`
- Modify: `tests/test_github_integration.py`

**Step 1: Add failing test first**

Add an integration test that:

1. Gets the latest SOPS version with `get_latest_sops_version()`.
2. Gets the current platform download URL with `get_sops_download_url(platform.system(), platform.machine(), version)`.
3. Asserts the current platform has a SOPS release asset.
4. Calls a helper to download the binary and checksums into `tmp_path` through `gh release download`.
5. Asserts the binary and checksums exist.
6. Asserts `verify_sha256(binary_path, checksums_path, binary_name)` returns true.

Expected initial failure: `AttributeError` for the missing download helper.

**Step 2: Implement helper**

Add a helper near the SOPS install helpers:

```python
def download_sops_release_assets(version: str, binary_name: str, download_dir: str) -> tuple[str, str]:
    checksums_name = f"sops-{version}.checksums.txt"
    try:
        subprocess.run(
            [
                "gh", "release", "download", version,
                "--repo", "getsops/sops",
                "--pattern", binary_name,
                "--pattern", checksums_name,
                "--dir", download_dir,
            ],
            check=True,
        )
    except FileNotFoundError:
        print("GitHub CLI `gh` is required for installing sops. Install gh first.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Failed to download sops release assets with gh: {e}", file=sys.stderr)
        sys.exit(1)

    return os.path.join(download_dir, binary_name), os.path.join(download_dir, checksums_name)
```

**Step 3: Update installer to use helper**

In `download_and_install_sops()`, replace inline `gh release download` logic with `download_sops_release_assets()` so the integration test covers the same download path used by install. Keep SOPS version discovery and release download reachable only from the `install` command or direct helper tests; `import-keys` and `updatekeys` must not call them.

**Step 4: Run test and verify pass**

Run:

```bash
uv run --with pytest pytest -v tests/test_github_integration.py
```

Expected: all integration tests pass.

---

## Task 4: Add pre-push hook

**Files:**
- Create: `.githooks/pre-push`

**Step 1: Create hook**

Write:

```sh
#!/bin/sh
set -eu

uv run --with pytest pytest -v tests/test_github_integration.py
```

**Step 2: Make executable**

Run:

```bash
chmod +x .githooks/pre-push
```

**Step 3: Enable hooks locally**

Run:

```bash
git config core.hooksPath .githooks
```

**Step 4: Verify hook blocks/passes by running directly**

Run:

```bash
.githooks/pre-push
```

Expected: integration tests pass. Missing `gh` authentication or missing public SSH keys are failures and block push.

---

## Task 5: Verification

**Files:**
- Check: `github_to_sops/__init__.py`
- Check: `tests/test_github_integration.py`
- Check: `.githooks/pre-push`

Run:

```bash
python3 -m py_compile github_to_sops/__init__.py
uv run --with pytest pytest -v tests/test_github_integration.py
.githooks/pre-push
```

Expected: all pass.

---

## Task 6: Commit and push

**Files:**
- Add: `tests/test_github_integration.py`
- Add: `.githooks/pre-push`
- Add: `docs/plans/2026-06-16-github-integration-tests.md`
- Modify: `github_to_sops/__init__.py`

**Step 1: Commit**

Run:

```bash
git add github_to_sops/__init__.py tests/test_github_integration.py .githooks/pre-push docs/plans/2026-06-16-github-integration-tests.md
git commit -m "test: add GitHub integration coverage"
```

**Step 2: Push**

Run:

```bash
git push origin main
```

Expected: pre-push hook runs and blocks push on integration test failure.
