This script enables one to use github as a trusted public key distribution mechanism. SOPS enables git as a secret vault.

## Why?

I needed github-to-sops to make SOPS easier to use for my https://deepstructure.io and https://chatcraft.org projects.

This makes it easy to setup [SOPS](https://github.com/getsops/sops) as a lightweight gitops alternative to AWS Secrets Manager, AWS KMS, Hashicorp Vault.

SOPS is helpful to avoid the push-and-pray (https://dagger.io/ came up with this term and solution for it) pattern where all secrets for github actions are stored in [Github Secrets](https://docs.github.com/en/actions/security-guides/using-secrets-in-github-actions) such that nobody can repro stuff locally. With sops one can give github actions a single age private key and share all the development keys with rest of team on equal footing with CI/CD env.

## Requirements

* Python3
* [pip](https://pip.pypa.io/en/stable/installation/)
* https://github.com/Mic92/ssh-to-age/ (until the [SOPS ssh backend](https://github.com/getsops/sops/pull/1134) lands).

## Installation
The latest version of github-to-sops can be cloned locally or installed using pip:
```bash
pip install github-to-sops
```

On linux you can install sops,ssh-to-age using docker:
```bash
docker run --rm -v /usr/local/bin:/go/bin golang:latest go install github.com/Mic92/ssh-to-age/cmd/ssh-to-age@latest
docker run --rm -v /usr/local/bin:/go/bin golang:latest go install github.com/getsops/sops/cmd/sops@v3.8.1
```

## Implementation

This generates a nice .sops.yaml file with comments indicating where the keys came from to make key rotation easier.

Idea for this originated in https://github.com/tarasglek/chatcraft.org/pull/319 after I got sick of devising a secure secret distribution scheme for every small project.

## Contributions Welcome
* Tests
* Binary build for python-less environments
* Would be nice to add is ACLs and an integrity check to keys being used.

## Examples:

I wrote an indepth explanation and screencasts on my blog post introducing [github-to-sops](https://taras.glek.net/post/github-to-sops-lighter-weight-secret-management/#heres-how-you-get-started).

### Example workflow for secrets with github

import keys
```bash
./github-to-sops import-keys --github-url https://github.com/tarasglek/chatcraft.org --key-types ssh-ed25519 --format sops > .sops.yaml
```
lets see
```bash
cat .sops.yaml
```
```yaml
creation_rules:
  - key_groups:
      - age:
        - age19j4d6v9j7rx5fs629fu387qz4zmlpsqjexa4s08tkfrrmfdl5cwqjlaupd # humphd
        - age13runq29jhy9kfpaegczrzttykerswh0qprq59msgd754yermtfmsa3hwg2 # tarasglek
```

Put a sample secret in yaml

```bash
echo -e "secrets:\n  SECRET_KEY: dontlook" | sops --input-type yaml --output-type yaml  -e /dev/stdin > secrets.enc.yaml
```
Lets take a peek
```bash
head -n 9 secrets.enc.yaml
```
```yaml
secrets:
    SECRET_KEY: ENC[AES256_GCM,data:MKKR6B0h1iA=,iv:KegjC62NQxich1dtodVF3aVnchf/fB+KQbtETh+4CaY=,tag:2+5mk4YMKKxLqaCOpZVNSA==,type:str]
sops:
    kms: []
    gcp_kms: []
    azure_kv: []
    hc_vault: []
    age:
        - recipient: age19j4d6v9j7rx5fs629fu387qz4zmlpsqjexa4s08tkfrrmfdl5cwqjlaupd
```
^ is safe to commit!

#### Decrypting secrets using ssh keys

```bash
export SOPS_AGE_KEY=$(ssh-to-age -private-key < ~/.ssh/id_ed25519)
```

Lets extract our secret in a way that's useful for automation
```bash
sops --extract '["secrets"]["SECRET_KEY"]' -d secrets.env.yaml
```
```
dontlook
```

`sops -i secrets.env.yaml` is useful for interactive editing.

#### Bulk-updating secrets+keys when someone is added/removed from project

First command pulls the latest set of keys from people in github, the second re-encrypts. Note you need to be able to decrypt keys yourself using `sops -d` command above as a prereq.
```bash
fdfind -H  .sops.yaml$|xargs -n1 github-to-sops --local-github-checkout . --key-types ssh-ed25519  --inplace-edit 
fdfind enc.yaml|xargs -n1 sops updatekeys -y
```

### Misc Examples



## Usage:
```
./github-to-sops -h
usage: github-to-sops [-h] {import-keys,refresh-secrets} ...

Manage GitHub SSH keys and generate SOPS-compatible SSH key files.

options:
  -h, --help            show this help message and exit

Commands:
  {import-keys,refresh-secrets}
    import-keys         Import SSH keys of GitHub repository contributors or specified github users and output that info into a useful format like sops or ssh authorized_keys
    refresh-secrets     Find all .sops.yaml files in the repo that are managed by git and run `import-keys --inplace-edit .sops.yaml` on them.

Example invocations:
- `./github-to-sops import-keys --github-url https://github.com/tarasglek/chatcraft.org --key-types ssh-ed25519 --format sops`
- `./github-to-sops import-keys --github-url https://github.com/tarasglek/chatcraft.org --format authorized_keys`
- `./github-to-sops import-keys --local-github-checkout . --format sops --known-hosts ~/.ssh/known_hosts --key-types ssh-ed25519`
- `./github-to-sops refresh-secrets`
```

## Env vars:
*  GITHUB_TOKEN: optional github token which helps avoid rate limiting.
