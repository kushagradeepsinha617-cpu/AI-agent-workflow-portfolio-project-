"""Protect input files from accidental output/log aliases in the serial CLI."""
from itertools import combinations
from pathlib import Path


def same_file(left, right):
    left, right = Path(left), Path(right)
    return left.resolve() == right.resolve() or (
        left.exists() and right.exists() and left.samefile(right))


def require_distinct_files(paths):
    if any(same_file(left, right) for left, right in combinations(paths, 2)):
        raise ValueError('Input, output and log must use different files')
