"""KungFu Chess - entry point.

Repository: <insert-git-repository-url-here>
"""
import sys

from texttests.script_runner import run


def main():
    lines = [line.strip() for line in sys.stdin]
    run(lines)


if __name__ == "__main__":
    main()
