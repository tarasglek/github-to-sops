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
```python
pip install github-to-sops
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

generate keys
```bash
./github-to-sops --github-url https://github.com/tarasglek/chatcraft.org --key-types ssh-ed25519 --format sops > .sops.yaml
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

### Misc Examples

Generate keys from a local github checkout and add ssh hosts to it:

```bash
# note you can also make a "custom" known_hosts with ssh-keyscan 192.168.1.1 > /tmp/known_hosts
./github-to-sops --local-github-checkout . --format sops --known-hosts ~/.ssh/known_hosts --key-types ssh-ed25519
creation_rules:
  - key_groups:
      - age:
        - age13runq29jhy9kfpaegczrzttykerswh0qprq59msgd754yermtfmsa3hwg2 # tarasglek
        - age120ld5rvtsuavnlexa2kc7eahrg8egf4gwg22t0q44rcu2z3xegrq4364t4 # 192.168.1.1
```

For generating ssh authorized_keys:

```bash
./github-to-sops --github-url https://github.com/tarasglek/chatcraft.org --format authorized_keys
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIIedvn21UgBc1VcasThd+/U84Xfkrw+Ox5RIxufs5tJP humphd
ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIDzJmAWAOp6fQGs/+v1PT+0dgzG7XHwhJnvF+tL5TwJx tarasglek
```

## Usage:
```
./github-to-sops -h
usage: github-to-sops [-h] [--github-url GITHUB_URL | --local-github-checkout LOCAL_GITHUB_CHECKOUT] [--known-hosts KNOWN_HOSTS] [--github-users GITHUB_USERS] [--key-types KEY_TYPES] [--format {authorized_keys,ssh-to-age,sops}]

Fetch SSH keys of GitHub repository contributors or specified github users and output that info into a useful format like sops or ssh authorized_keys

options:
  -h, --help            show this help message and exit
  --github-url GITHUB_URL
                        GitHub repository URL.
  --local-github-checkout LOCAL_GITHUB_CHECKOUT
                        Path to local Git repository.
  --known-hosts KNOWN_HOSTS
                        Path to ssh known hosts to also fetch keys from
  --github-users GITHUB_USERS
                        Comma-separated list of GitHub usernames to fetch keys for.
  --key-types KEY_TYPES
                        Comma-separated types of SSH keys to fetch (e.g., ssh-ed25519,ssh-rsa). Pass no value for all types.
  --format {authorized_keys,ssh-to-age,sops,json}
                        Output/convert keys using the specified format. Supported formats: authorized_keys, ssh-to-age, sops. For example, use '--format ssh-to-age' to convert SSH keys to age keys.

Example invocations: `./github-to-sops --github-url https://github.com/tarasglek/chatcraft.org --key-types ssh-ed25519 --format sops` `./github-to-sops --github-url https://github.com/tarasglek/chatcraft.org --format authorized_keys` `./github-to-sops --local-github-
checkout . --format sops --known-hosts ~/.ssh/known_hosts --key-types ssh-ed25519`
```

## Env vars:
*  GITHUB_TOKEN: optional github token which helps avoid rate limiting.
