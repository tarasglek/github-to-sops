import re
import sys
def process_template(template, tag):
    """
        1. takes a template like above
    2. finds line containing GITHUB_TO_SOPS_TAG
    3. Detects whitespace on GITHUB_TO_SOPS_TAG line and stores that as line_prefix
    4. returns a string with all previous lines before GITHUB_TO_SOPS_TAG as prefix
    5. Finds first line after GITHUB_TO_SOPS_TAG with a different prefix
    6. returns all lines after prefix changed as suffix
    7. Only does it once, eg subsequent GITHUB_TO_SOPS_TAG lines will end up in suffix"""
    lines = template.split("\n")
    prefix = []
    suffix = []
    found_tag = False
    tag_line_prefix = None
    scan_prefix = None
    for line in lines:
        if tag in line and not found_tag:
            found_tag = True
            # Match only the leading whitespace of the line with the tag
            match = re.match(r"^\s*", line)
            scan_prefix= tag_line_prefix = match.group() if match else ""
            continue

        if found_tag:
            # Compute the current line's prefix
            current_line_prefix = re.match(r"^\s*", line).group()
            # Check if the current line's prefix is different from the tag's prefix
            if current_line_prefix != scan_prefix:
                suffix.append(line)
                scan_prefix = None
        else:
            prefix.append(line)

    return tag_line_prefix, "\n".join(prefix), "\n".join(suffix)

def main():
    import json
    line_prefix, before, after = process_template(sys.stdin.read(), "GITHUB_TO_SOPS_TAG")
    print(before)
    print(line_prefix + "- yo yo")
    print(after)

if __name__ == "__main__":
    main()