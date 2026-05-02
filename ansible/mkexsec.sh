#!/bin/bash

INPUT_FILE="secrets.yaml"
OUTPUT_FILE="example.secrets.yaml"

if [ ! -f "$INPUT_FILE" ]; then
    echo "Error: '$INPUT_FILE' not found!"
    exit 1
fi

echo "Generating $OUTPUT_FILE from $INPUT_FILE..."

# The sed command searches for YAML keys or list items and replaces their values
# Regex breakdown:
# - ^                           Start of line
# - (                           Start capture group 1 (we keep this part)
#   - [[:space:]]*              Any leading indentation
#   - ([a-zA-Z0-9_.-]+:|-)      A YAML key ending in a colon, OR a list dash
#   - [[:space:]]+              At least one space
# - )                           End capture group 1
# - [^[:space:]#].*$            Any value that isn't empty or an inline comment
SED_REGEX='s/^([[:space:]]*([a-zA-Z0-9_.-]+:|-)[[:space:]]+)[^[:space:]#].*$/\1<change me>/'

# Check if the file is fully encrypted with Ansible Vault
if head -n 1 "$INPUT_FILE" | grep -q '^\$ANSIBLE_VAULT'; then
    echo "Ansible Vault encryption detected. You may be prompted for your vault password."
    # Use ansible-vault to decrypt on the fly, redact, and write to the output file
    ansible-vault view "$INPUT_FILE" | sed -E "$SED_REGEX" > "$OUTPUT_FILE"
else
    # Process as a plain text YAML file
    sed -E "$SED_REGEX" "$INPUT_FILE" > "$OUTPUT_FILE"
fi

echo "Done! Please review $OUTPUT_FILE before committing to GitHub."
