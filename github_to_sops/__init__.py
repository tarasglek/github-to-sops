#!/usr/bin/env python3
"""
Standalone (no-dependencies beyond Python) script fetches SSH keys of GitHub repository contributors and generates SOPS-compatible SSH key files.
"""

import argparse
import json
import logging
import os
import sys
import subprocess
from typing import Any, Dict, Optional, List, Set, TextIO
from urllib import request, error
import re

GITHUB_TO_SOPS_TAG = "https://github.com/tarasglek/github-to-sops"
GITHUB_API_BASE_URL = "api.github.com/repos"
GENERATED_MSG = (
    f"Generated by `{' '.join(sys.argv)}` {GITHUB_TO_SOPS_TAG}"
)

SOPS_TEMPLATE = f"""
creation_rules:
  - key_groups:
      - age:
        - Mark stuff to replace by having a line with {GITHUB_TO_SOPS_TAG} which can be within a comment or not
        - Following lines with same indent get dropped
# EOF
"""

def process_template(template, tag, output_fd):
    """
    1. Takes a template string
    2. Finds line containing the specified tag
    3. Detects whitespace on the tag line and stores that as line_prefix
    4. yields it
    5. Finds first line after the tag with a different prefix
    6. Prints all other lines to console as they are being scanned
    7. Only does it once, e.g., subsequent tag lines will end up with suffix
    8. Yields None if no tag was found
    """
    lines = template.split("\n")
    found_tag = False
    scan_prefix = None
    tag_pattern = re.compile(r"^\s*")  # Precompile the regex pattern

    for line in lines:
        if not found_tag:
            if tag in line:
                found_tag = True
                # Match only the leading whitespace of the line with the tag
                match = tag_pattern.match(line)
                scan_prefix = match.group() if match else ""
                yield scan_prefix
                continue
            output_fd.write(line + "\n")
        else:
            if scan_prefix is not None:
                # Compute the current line's prefix
                current_line_prefix = tag_pattern.match(line).group()
                # Check if the current line's prefix is different from the tag's prefix
                if current_line_prefix == scan_prefix:
                    continue
                scan_prefix = None
            output_fd.write(line + "\n")
    if not found_tag:
        yield None

def get_api_url_from_git(repo_path: str) -> Optional[str]:
    """
    Extract the GitHub API URL from the local git repository using git command.

    :param repo_path: Path to the local git repository.
    :return: GitHub API URL or None if not found.
    """
    try:
        # Get the remote URL of the 'origin' remote repository
        git_url = (
            subprocess.check_output(
                ["git", "-C", repo_path, "remote", "get-url", "origin"]
            )
            .decode()
            .strip()
        )

        # Transform the git URL to the GitHub API URL
        if git_url.startswith("https://github.com/"):
            return git_url.replace(
                "https://github.com/", GITHUB_API_BASE_URL + "/", 1
            ).rstrip(".git")
        elif git_url.startswith("git@github.com:"):
            return git_url.replace(
                "git@github.com:", GITHUB_API_BASE_URL + "/", 1
            ).rstrip(".git")
    except Exception as e:
        print(f"Unexpected error: {e}", file=sys.stderr)
    return None


def get_api_url(repo_url: Optional[str], local_repo: Optional[str]) -> str:
    """
    Determine the GitHub API URL from either a repository URL or a local repository path.

    :param repo_url: GitHub repository URL.
    :param local_repo: Path to local Git repository.
    :return: GitHub API URL.
    :raises ValueError: If neither a repository URL nor a local repository path is provided.
    """
    api_url = None
    if repo_url:
        api_url = repo_url.rstrip("/").replace("github.com", GITHUB_API_BASE_URL, 1)
    elif local_repo:
        api_url = get_api_url_from_git(local_repo)
    if api_url:
        if not api_url.startswith("https://"):
            api_url = f"https://{api_url}"
        return api_url
    else:
        raise ValueError(
            "Unable to determine the repository URL from the local Git repository."
        )


def github_request(request_url: str, method: str = 'GET', data: Optional[dict] = None) -> request.urlopen:
    """
    Make a request to the GitHub API, supporting both GET and POST requests.
    This injects the GitHub API token environment variable into the request if present.

    :param request_url: URL to make the request to.
    :param method: HTTP method ('GET' or 'POST').
    :param data: Data to be sent in the request body (for POST requests).
    :return: Response from the GitHub API.
    """
    if data is not None:
        data = json.dumps(data).encode()
    req = request.Request(request_url, data=data, method=method)
    github_token = os.getenv("GITHUB_TOKEN")
    if github_token:
        auth_header = f"token {github_token}"
        req.add_header("Authorization", auth_header)
    req.add_header("Content-Type", "application/json")
    return request.urlopen(req)

def fetch_contributors(api_url: str) -> List[str]:
    """
    Fetch the list of contributors for a GitHub repository using GitHub's GraphQL API.
    If the GraphQL query fails, fallback to the REST API.

    :param api_url: GitHub API URL for the repository.
    :return: List of contributor usernames.
    """
    graphql_url = "https://api.github.com/graphql"
    owner, repo = api_url.split('/')[-2:]
    query = """
    query {
      repository(owner: "%s", name: "%s") {
        collaborators(first: 100) {
          edges {
            node {
              login
            }
          }
        }
      }
    }
    """ % (owner, repo)

    try:
        with github_request(graphql_url, 'POST', {'query': query}) as response:
            data = json.load(response)
            contributors = data['data']['repository']['collaborators']['edges']
            return [contributor['node']['login'] for contributor in contributors]
    except (error.HTTPError, TypeError) as e:
        error_type = "HTTPError" if isinstance(e, error.HTTPError) else "KeyError"
        logging.error(f"{error_type} when querying {graphql_url}: {e}")
        logging.info("Attempting to list users via REST API as a fallback")
        return fetch_contributors_rest(api_url)


def fetch_contributors_rest(api_url: str) -> List[str]:
    """
    Fallback method to fetch the list of contributors for a GitHub repository using the REST API.

    :param api_url: GitHub API URL for the repository.
    :return: List of contributor usernames.
    """
    url = f"{api_url}/contributors"
    try:
        with github_request(url) as response:
            contributors = json.load(response)
            logging.debug(f"{url} returned {json.dumps(contributors, indent=2)}")
            return [contributor["login"] for contributor in contributors]
    except error.HTTPError as e:
        logging.error(f"HTTP Error: {e.code} {e.reason}")
        logging.error(
            "For private repositories and to avoid throttling you must set the GITHUB_TOKEN. Alternatively, consider passing users explicitly via --github-users to avoid auth hassles."
        )
        return []


def convert_key_to_age(key: str) -> Optional[str]:
    """
    Convert an SSH key to an age key using ssh-to-age.

    :param key: The SSH key to convert.
    :return: The age key or None if conversion fails.
    """
    try:
        result = subprocess.run(
            ["ssh-to-age"], input=key, stdout=subprocess.PIPE, text=True, check=True
        )
        return result.stdout.strip()
    except Exception as e:
        print(f"Error running ssh-to-age: {e}", file=sys.stderr)
    return None


def fetch_github_ssh_keys(contributors: List[str]) -> Dict[str, Dict[str, List[str]]]:
    """
    Fetch and output the specified types of SSH keys for a list of GitHub users.
    Store each key type mapping to a list of keys.

    :param contributors: List of GitHub usernames.
    :return: A dictionary mapping usernames to dictionaries of key types and their keys.
    """
    keys_by_user_and_type = {}
    for username in contributors:
        user_keys = keys_by_user_and_type.get(username, {})
        try:
            with github_request(f"https://github.com/{username}.keys") as response:
                lines = response.read().decode().strip().splitlines()
                for line in lines:
                    key_type, key = line.split(" ", 1)  # Split on first space only
                    if key_type not in user_keys:
                        user_keys[key_type] = []
                    user_keys[key_type].append(key)
                keys_by_user_and_type[username] = user_keys
        except error.HTTPError as e:
            print(
                f"HTTP Error: {e.code} {e.reason} for user {username}", file=sys.stderr
            )
            continue
    return keys_by_user_and_type


def iterate_keys(
    keys: dict,
    accepted_key_types: Optional[Set[str]] = None,
):
    """
    Print keys in useful formats

    :param key_types: The types of SSH keys to fetch (e.g., ['ssh-ed25519', 'ssh-rsa']) or None for all keys.
    :param convert_to_age: Whether to convert the keys to age keys.
    """
    for username, user_keys in keys.items():
        if accepted_key_types is not None:
            accepted_keys = set(user_keys.keys()).intersection(accepted_key_types)
        else:
            accepted_keys = user_keys.keys()
        if not accepted_keys:
            print(
                f"User {username} does not have any of the accepted key types: {','.join(list(accepted_key_types))}.",
                file=sys.stderr,
            )
        for key_type in accepted_keys:
            key = user_keys[key_type]
            yield {"username": username, "key_type": key_type, "key": key}

def ssh_keyscan(hosts: List[str], parsed_keys: Dict[str, Dict[str, List[str]]] = None) -> Dict[str, Dict[str, List[str]]]:
    """
    Perform an SSH key scan for a list of hosts and parse the known hosts content.

    :param hosts: A list of hostnames or IP addresses to scan.
    :param parsed_keys: An optional dictionary to which the scan results will be added.
                        If not provided, a new dictionary will be created.
    :return: A dictionary mapping each host to a dictionary of key types and their keys.
             Each key type maps to a list of keys to accommodate multiple keys of the same type.
    """
    if parsed_keys is None:
        parsed_keys = {}

    def ssh_keyscan_inner(host: str) -> str:
        """
        Run the ssh-keyscan command for a single host and return its output.

        :param host: The hostname or IP address to scan.
        :return: The stdout from the ssh-keyscan command.
        :raises Exception: If ssh-keyscan fails.
        """
        try:
            result = subprocess.run(
                ["ssh-keyscan", host],
                check=True,
                stdout=subprocess.PIPE,
                text=True
            )
            return result.stdout
        except subprocess.CalledProcessError as e:
            raise Exception(f"ssh-keyscan failed with exit code {e.returncode}: {e.stderr}")

    def parse_known_hosts_content(known_hosts: str, parsed_keys: Dict[str, Dict[str, List[str]]]):
        """
        Parse the content of known hosts and update the parsed_keys dictionary.

        :param known_hosts: The stdout from the ssh-keyscan command.
        :param parsed_keys: The dictionary to which the scan results will be added.
        """
        for line in known_hosts.splitlines():
            if line.startswith("#") or line.strip() == "":
                continue

            parts = line.strip().split()
            if len(parts) < 3:
                continue

            host, key_type, key = parts[0], parts[1], parts[2]
            if host not in parsed_keys:
                parsed_keys[host] = {}
            if key_type not in parsed_keys[host]:
                parsed_keys[host][key_type] = []
            parsed_keys[host][key_type].append(key)

    for host in hosts:
        known_hosts_log = ssh_keyscan_inner(host)
        parse_known_hosts_content(known_hosts_log, parsed_keys)

    return parsed_keys

def is_tool_available(name):
    """Check if a tool is available on the system."""
    try:
        subprocess.run(
            [name, "--version"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=True,
        )
        return True
    except (OSError, subprocess.CalledProcessError):
        return False


def comma_separated_list(string: str) -> Set[str]:
    """
    Converts a comma-separated string into a set of strings.

    :param string: A string containing comma-separated values.
    :return: A set containing the individual values as strings.
    """
    return set(string.split(","))


def print_keys(template: str, user_keys: Dict[str, Dict[str, List[str]]],
               accepted_key_types: Set[str], output_format: str,
               output_fd: TextIO) -> None:
    """
    Processes a template and prints SSH keys in a specified format.

    :param template: A string template for processing.
    :param user_keys: A dictionary mapping usernames to dictionaries of key types and their keys.
                      Each key type maps to a list of keys.
    :param accepted_key_types: A set of accepted key types.
    :param output_format: The format in which to output the keys.
    :param output_fd: The file descriptor to write the output to.
    """
    # Assuming process_template is a function you have defined elsewhere
    for line_prefix in process_template(template, GITHUB_TO_SOPS_TAG, output_fd):
        if line_prefix is None:
            line_prefix = ""
        print(f"{line_prefix}# {GENERATED_MSG}", file=output_fd)

        # Sort the users by their username
        sorted_users = sorted(user_keys.keys(), key=lambda username: username.lower())

        for username in sorted_users:
            user_key_types = user_keys[username]
            for key_type in user_key_types:
                if accepted_key_types is not None and key_type not in accepted_key_types:
                    continue
                for key in user_key_types[key_type]:
                    if output_format in ["ssh-to-age", "sops"]:
                        # Assuming convert_key_to_age is a function you have defined elsewhere
                        key = convert_key_to_age(f"{key_type} {key}")
                        if not key:
                            print(
                                f"Skipped converting {key_type} key for user {username} to age key with ssh-to-age",
                                file=sys.stderr,
                            )
                            continue
                        if output_format == "sops":
                            print(f"{line_prefix}- {key} # {username}", file=output_fd)
                        else:
                            print(f"{key}", file=output_fd)
                    else:
                        print(f"{key_type} {key} {username}", file=output_fd)


def refresh_secrets(args):
    """
    Find all .sops.yaml files in the repo that are managed by git and run `import-keys --inplace-edit .sops.yaml` on them.
    """
    import subprocess
    import os
    import logging

    # Configure logging to output to stderr
    logging.basicConfig(level=logging.INFO, format='%(message)s', stream=sys.stderr)

    def find_sops_yaml_files():
        """
        Find all .sops.yaml files in the repo that are managed by git.
        """
        logging.info("Finding .sops.yaml files in the repo managed by git.")
        result = subprocess.run(
            ["git", "ls-files", "*.sops.yaml"],
            stdout=subprocess.PIPE,
            text=True,
            check=True
        )
        return result.stdout.splitlines()

    sops_yaml_files = find_sops_yaml_files()
    logging.info(f"Found {len(sops_yaml_files)} .sops.yaml files.")
    for file in sops_yaml_files:
        logging.info(f"Running import-keys --inplace-edit on {file}.")
        subprocess.run(
            [sys.argv[0], "import-keys", "--inplace-edit", file],
            check=True
        )

def generate_keys(args):
    """
    Main func
    """
    if args.inplace_edit:
        args.format = "sops"
        input_template = open(args.inplace_edit, "r").read()
        output_fd = open(args.inplace_edit + ".tmp", "w")
        if args.key_types is None:
            args.key_types = set(["ssh-ed25519"])

    api_url = get_api_url(args.github_url, args.local_github_checkout)
    if args.github_users:
        contributors = args.github_users
    else:
        contributors = fetch_contributors(api_url)

    keys = fetch_github_ssh_keys(contributors)

    if args.ssh_hosts:
        keys = ssh_keyscan(args.ssh_hosts, keys)

    print_keys(
        template=input_template.strip() if args.inplace_edit else SOPS_TEMPLATE,
        user_keys=keys,
        accepted_key_types=args.key_types,
        output_format=args.format,
        output_fd=output_fd if args.inplace_edit else sys.stdout,
    )
    if args.inplace_edit:
        output_fd.close()
        os.rename(args.inplace_edit + ".tmp", args.inplace_edit)
def main():
    parser = argparse.ArgumentParser(
        description="Manage GitHub SSH keys and generate SOPS-compatible SSH key files."
    )
    subparsers = parser.add_subparsers(dest="command")

    refresh_secrets_parser = subparsers.add_parser(
        "refresh-secrets",
        help="Find all .sops.yaml files in the repo that are managed by git and run `import-keys --inplace-edit .sops.yaml` on them."
    )
    refresh_secrets_parser.add_argument(
        "-v",
        "--verbose",
        help="Turn on debug logging to see HTTP requests and other internal Python stuff.",
        action="store_true",
    )

    import_keys_parser = subparsers.add_parser(
        "import-keys",
        help="Import SSH keys of GitHub repository contributors or specified github users and output that info into a useful format like sops or ssh authorized_keys",
        epilog=f"""Example invocations:
`{sys.argv[0]} import-keys --github-url https://github.com/tarasglek/chatcraft.org --key-types ssh-ed25519 --format sops`
`{sys.argv[0]} import-keys --github-url https://github.com/tarasglek/chatcraft.org --format authorized_keys`
`{sys.argv[0]} import-keys --local-github-checkout . --format sops --ssh-hosts 192.168.1.1,192.168.1.2 --key-types ssh-ed25519`
""",
    )
    import_keys_parser.add_argument("--github-url", help="GitHub repository URL.")
    import_keys_parser.add_argument("--local-github-checkout", default=".", help="Path to local Git repository.")
    import_keys_parser.add_argument(
        "--ssh-hosts",
        type=comma_separated_list,
        help="Comma-separated list of ssh servers to fetch public keys from."
    )
    import_keys_parser.add_argument(
        "--github-users",
        type=comma_separated_list,
        help="Comma-separated list of GitHub usernames to fetch keys for.",
    )
    import_keys_parser.add_argument(
        "--key-types",
        type=comma_separated_list,
        default=None,
        help="Comma-separated types of SSH keys to fetch (e.g., ssh-ed25519,ssh-rsa). Pass no value for all types.",
    )
    # Supported conversions with validation
    supported_conversions = ["authorized_keys", "ssh-to-age", "sops"]
    import_keys_parser.add_argument(
        "--format",
        default=supported_conversions[0],
        type=str,
        choices=supported_conversions,
        help=f"Output/convert keys using the specified format. Supported formats: "
        f"{', '.join(supported_conversions)}. For example, use '--format "
        f"ssh-to-age' to convert SSH keys to age keys.",
    )
    import_keys_parser.add_argument(
        "--inplace-edit",
        help="Edit SOPS file in-place. This takes a .sops.yaml file as input and replaces it. This sets --format to sops",
    )
    import_keys_parser.add_argument(
        "-v",
        "--verbose",
        help="Turn on debug logging to see HTTP requests and other internal Python stuff.",
        action="store_true",
    )

    args = parser.parse_args()

    if args.command == "import-keys":
        generate_keys(args)  # Function name remains the same as it handles the logic
    elif args.command == "refresh-secrets":
        refresh_secrets(args)
    else:
        parser.print_help()

if __name__ == "__main__":
    main()
