#!/bin/bash

# Run Pylint on the project
echo "Running Pylint checks..."

# Specify the directories or files you want to check with pylint
FILES="authentication tests"

# Run pylint on the specified files
pylint $FILES
if [ $? -ne 0 ]; then
    echo "Pylint checks failed. Commit aborted."
    exit 1
fi

echo "Pylint checks passed. Proceeding with commit."
