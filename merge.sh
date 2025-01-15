#!/bin/bash

# Check if exactly two arguments are provided
if [ "$#" -ne 2 ]; then
    echo "Usage: $0 <URL or file> <target file>"
    exit 1
fi

# Assign input arguments to variables
URL_OR_FILE="$1"
TARGET_FILE="$2"

# Execute the docker command with the given inputs
docker run --rm -it -v "$(pwd):/app" --workdir /app python:3 \
    python merge.py -rnft "$TARGET_FILE" \
    "$URL_OR_FILE" customized.dconf
