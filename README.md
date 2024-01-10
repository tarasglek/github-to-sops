This script enables one to use github as a trusted public key distribution mechanism.

It's written for use with sops via the age backend (until the [sops ssh backend](https://github.com/getsops/sops/pull/1134) lands).

## Usage:

With sops:

```bash
./github-to-age --github-url https://github.com/tarasglek/chatcraft.org --key-types ssh-ed25519 --format sops
creation_rules:
  - key_groups:
      - age:
        - age19j4d6v9j7rx5fs629fu387qz4zmlpsqjexa4s08tkfrrmfdl5cwqjlaupd # humphd
        - age13runq29jhy9kfpaegczrzttykerswh0qprq59msgd754yermtfmsa3hwg2 # tarasglek
```

With ssh:

```bash
./github-to-age --github-url https://github.com/tarasglek/chatcraft.org --format authorized_keys
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIedvn21UgBc1VcasThd+/U84Xfkrw+Ox5RIxufs5tJP humphd
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDzJmAWAOp6fQGs/+v1PT+0dgzG7XHwhJnvF+tL5TwJx tarasglek
```
## Env vars:
*  GITHUB_TOKEN: optional github token which helps avoid rate limiting.