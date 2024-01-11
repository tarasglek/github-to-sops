import re
import sys
def process_template(template, tag, output_fd):
    """
    1. Takes a template string
    2. Finds line containing the specified tag
    3. Detects whitespace on the tag line and stores that as line_prefix
    4. Returns a string with all previous lines before the tag as prefix
    5. Finds first line after the tag with a different prefix
    6. Returns all lines after prefix changed as suffix
    7. Only does it once, e.g., subsequent tag lines will end up in suffix
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

def main():
    tag = "GITHUB_TO_SOPS_TAG"
    import os
    for line_prefix in process_template(sys.stdin.read(), tag, sys.stdout):
        print(line_prefix + "#" + tag)
        print(line_prefix + f"- yo yo {os.getpid()}" )

if __name__ == "__main__":
    main()