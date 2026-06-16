# Security Hardening Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Fix the real remaining security issues in `github-to-sops` after deciding to use `gh`: remove contributor-based trust and secure the `sops` installer.

**Architecture:** Repository recipient discovery uses `gh api repos/OWNER/REPO/collaborators`; `gh` owns GitHub authentication, host handling, pagination, and API access. This tool only resolves a GitHub remote/URL into an `OWNER/REPO` string for `gh`. The installer downloads `sops` release assets with `gh release download` into a private temporary directory, verifies the downloaded binary against the upstream SHA256 checksum, then installs it.

**Tech Stack:** Python standard library (`argparse`, `subprocess`, `urllib.parse`, `hashlib`, `tempfile`, `logging`, `os`), external `gh` CLI for repository collaborator lookup and `sops` release downloads, external `sudo` only for final `sops` install move.

---

## Design

### Security fixes covered

1. Remove `/contributors` fallback completely.
2. Use `gh api` to list repository collaborators.
3. Remove application-managed GitHub API auth/token handling because `gh` owns auth.
4. Harden `install` by using `gh release download`, a private temp directory, and SHA256 checksum verification.

### Explicitly not in scope

- No `updatekeys` replay hardening.
- No custom GitHub GraphQL/REST collaborator client.
- No extra GitHub token/enterprise/host logic beyond invoking `gh`.

### User-visible behavior

- `--github-users` still works without `gh`.
- Repository-based imports require `gh` and working `gh` authentication.
- Contributors are never used as SOPS recipients.
- `install` refuses to install if `gh release download` or checksum verification fails.

---

## Task 1: Resolve GitHub repo to `OWNER/REPO`

**Files:**
- Modify: `github_to_sops/__init__.py`

**Step 1: Add import**

Add:

```python
from urllib.parse import urlparse
```

**Step 2: Replace API URL conversion helpers**

Replace `get_api_url_from_git()` / `get_api_url()` with helpers that return raw remote URL and parse it to `OWNER/REPO`:

```python
def get_git_remote_url(repo_path: str) -> Optional[str]:
    if not is_git_repo(repo_path):
        logging.warning(f"The path '{repo_path}' is not a git repository. Not pulling keys from github.")
        return None
    try:
        git_url = subprocess.check_output(
            ["git", "-C", repo_path, "remote", "get-url", "origin"],
            stderr=subprocess.PIPE,
        ).decode().strip()
        logging.info(f"Pulling keys from GitHub repository: {git_url}")
        return git_url
    except Exception as e:
        logging.error(f"Unexpected error: {e}")
        return None


def parse_github_owner_repo(repo_url: str) -> Optional[str]:
    repo_url = repo_url.strip()

    if repo_url.startswith("git@github.com:"):
        path = repo_url.removeprefix("git@github.com:")
        parts = path.strip("/").split("/")
    else:
        parsed = urlparse(repo_url)
        if parsed.netloc != "github.com":
            logging.error(f"Unsupported GitHub repository URL: {repo_url}")
            return None
        parts = parsed.path.strip("/").split("/")

    if len(parts) < 2 or not parts[0] or not parts[1]:
        logging.error(f"Could not determine GitHub owner/repo from: {repo_url}")
        return None

    owner = parts[0]
    repo = parts[1].removesuffix(".git")
    return f"{owner}/{repo}"


def get_owner_repo(repo_url: Optional[str], local_repo: Optional[str]) -> Optional[str]:
    if repo_url:
        return parse_github_owner_repo(repo_url.rstrip("/"))
    if local_repo:
        git_url = get_git_remote_url(local_repo)
        if git_url:
            return parse_github_owner_repo(git_url)
    return None
```

**Step 3: Remove unused constant**

Delete `GITHUB_API_BASE_URL` if no longer used.

---

## Task 2: Use `gh api` for collaborators and remove contributors fallback

**Files:**
- Modify: `github_to_sops/__init__.py`

**Step 1: Add collaborator lookup**

Add:

```python
def fetch_collaborators(owner_repo: str) -> Optional[List[str]]:
    endpoint = f"repos/{owner_repo}/collaborators"
    try:
        result = subprocess.run(
            ["gh", "api", endpoint, "--paginate", "--jq", ".[].login"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True,
        )
    except FileNotFoundError:
        logging.error("GitHub CLI `gh` is required for repository collaborator lookup. Install gh or pass --github-users.")
        return None
    except subprocess.CalledProcessError as e:
        logging.error(f"Failed to fetch GitHub collaborators with gh: {e.stderr.strip()}")
        logging.error("Run `gh auth login` or pass explicit users via --github-users.")
        return None

    return [line.strip() for line in result.stdout.splitlines() if line.strip()]
```

**Step 2: Delete old repository lookup functions**

Delete:

```python
def fetch_contributors(...):
    ...

def fetch_contributors_rest(...):
    ...
```

This removes both the custom GraphQL collaborator client and the `/contributors` fallback.

**Step 3: Update `generate_keys()`**

Use `OWNER/REPO` and collaborators:

```python
owner_repo = get_owner_repo(args.github_url, args.local_github_checkout)
recipients = None
if args.github_users:
    recipients = args.github_users
elif owner_repo:
    recipients = fetch_collaborators(owner_repo)
    if recipients is None:
        logging.error("Failed to fetch collaborators from GitHub. Aborting to prevent data loss.")
        sys.exit(1)

keys = {}
if recipients:
    keys = fetch_github_ssh_keys(recipients)
```

---

## Task 3: Remove application-managed GitHub auth

**Files:**
- Modify: `github_to_sops/__init__.py`

**Step 1: Simplify `github_request()`**

`github_request()` remains only for public `https://github.com/{username}.keys` lookups. Replace it with:

```python
def github_request(request_url: str, method: str = 'GET', data: Optional[dict] = None) -> request.urlopen:
    if data is not None:
        data = json.dumps(data).encode()
    req = request.Request(request_url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    return request.urlopen(req)
```

**Step 2: Verify no app-managed GitHub auth remains**

Run:

```bash
rg -n "GITHUB_TOKEN|Authorization|auth_header" github_to_sops/__init__.py
```

Expected: no matches.

---

## Task 4: Secure `sops` installer with `gh release download` and checksum verification

**Files:**
- Modify: `github_to_sops/__init__.py`

**Step 1: Add checksum verification helper**

Add:

```python
def verify_sha256(binary_path: str, checksums_path: str, binary_name: str) -> bool:
    with open(checksums_path, "r") as f:
        checksums = f.read().splitlines()

    expected = None
    for line in checksums:
        fields = line.split()
        if len(fields) >= 2 and fields[1] == binary_name:
            expected = fields[0]
            break

    if expected is None:
        logging.error(f"Could not find checksum for {binary_name}")
        return False

    h = hashlib.sha256()
    with open(binary_path, "rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)

    actual = h.hexdigest()
    if actual != expected:
        logging.error(f"Checksum mismatch for {binary_name}: expected {expected}, got {actual}")
        return False
    return True
```

Also import:

```python
import hashlib
```

**Step 2: Download release assets with `gh` into private temporary directory**

Replace predictable `/tmp/sops` and direct `urllib` download logic with:

```python
binary_name = os.path.basename(download_url)
checksums_name = f"sops-{version}.checksums.txt"
with tempfile.TemporaryDirectory(prefix="github-to-sops-") as temp_dir:
    print(f"Downloading {binary_name} and {checksums_name} from getsops/sops {version}")
    try:
        subprocess.run(
            [
                "gh", "release", "download", version,
                "--repo", "getsops/sops",
                "--pattern", binary_name,
                "--pattern", checksums_name,
                "--dir", temp_dir,
            ],
            check=True,
        )
    except FileNotFoundError:
        print("GitHub CLI `gh` is required for installing sops. Install gh first.", file=sys.stderr)
        sys.exit(1)
    except subprocess.CalledProcessError as e:
        print(f"Failed to download sops release assets with gh: {e}", file=sys.stderr)
        sys.exit(1)

    temp_binary_path = os.path.join(temp_dir, binary_name)
    checksums_path = os.path.join(temp_dir, checksums_name)

    if not verify_sha256(temp_binary_path, checksums_path, binary_name):
        print("Checksum verification failed", file=sys.stderr)
        sys.exit(1)

    os.chmod(temp_binary_path, 0o755)
    subprocess.run(["sudo", "mv", temp_binary_path, "/usr/local/bin/sops"], check=True)
```

---

## Task 5: Update docs

**Files:**
- Modify: `README.md`

**Step 1: Update requirements**

Add:

```markdown
* [GitHub CLI (`gh`)](https://cli.github.com/) for repository collaborator lookup and for the `install` helper. Run `gh auth login` before using repository-based imports. If you pass recipients explicitly with `--github-users`, `gh` is not required for key import, but it is required for `github-to-sops install`.
```

**Step 2: Replace old `GITHUB_TOKEN` guidance**

Replace old env var guidance with:

```markdown
### GitHub authentication

`github-to-sops` uses GitHub collaborators for repository-based imports. It does not use GitHub contributors as secret recipients, because commit authors are not necessarily current trusted repository members.

For repository-based imports, install GitHub CLI and authenticate:

```bash
gh auth login
```

Alternatively, bypass repository lookup and pass explicit users:

```bash
github-to-sops --github-users alice,bob import-keys
```
```

**Step 3: Document install integrity**

In install docs, mention `github-to-sops install` downloads `sops` release assets with `gh release download` and verifies the binary against upstream SHA256 checksums before installation.

---

## Task 6: Verification

**Files:**
- Check: `github_to_sops/__init__.py`
- Check: `README.md`

**Step 1: Compile**

Run:

```bash
python3 -m py_compile github_to_sops/__init__.py
```

Expected: no output, exit code 0.

**Step 2: Explicit users path**

Run:

```bash
./github-to-sops --github-users tarasglek import-keys --format authorized_keys | head
```

Expected: prints public keys; does not require `gh`.

**Step 3: Repository collaborator path**

Run with `gh` authenticated:

```bash
./github-to-sops import-keys --format authorized_keys | head
```

Expected: uses collaborators via `gh`; no contributors.

**Step 4: Static checks**

Run:

```bash
rg -n "/contributors|fetch_contributors_rest|GITHUB_TOKEN|Authorization|auth_header|graphql|collaborators\(first" github_to_sops README.md
```

Expected: no app-managed GitHub auth, no contributors fallback, no GraphQL query. `gh` references are expected.

---

## Task 7: Commit

**Files:**
- Add: `docs/plans/2026-06-16-security-hardening.md`
- Modify: `github_to_sops/__init__.py`
- Modify: `README.md`

**Step 1: Review diff**

Run:

```bash
git diff -- github_to_sops/__init__.py README.md docs/plans/2026-06-16-security-hardening.md
```

Expected: only security hardening changes and this plan.

**Step 2: Commit**

Run:

```bash
git add github_to_sops/__init__.py README.md docs/plans/2026-06-16-security-hardening.md
git commit -m "fix: harden GitHub key import and installer"
```
