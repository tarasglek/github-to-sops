This script enables one to use github as a trusted public key distribution mechanism.

It's written for use with sops via the age backend (until the [sops ssh backend](https://github.com/getsops/sops/pull/1134) lands).

Usage:
  github-to-age -l /local/path/to/checkout -u <optional comma-separated list of subset of usernames>

Env vars:
  GITHUB_TOKEN: optional github token which helps avoid rate limiting.