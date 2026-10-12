"""Example scorer for the `validate` hook: a toy problem.

Problem: largest sum-free subset of {1..n}. A construction file is a JSON
object {"n": int, "set": [ints]}. The scorer checks validity and returns the
set size (direction: max). Raises ValueError on an invalid construction.
"""

import json


def sum_free_size(path):
    with open(path, encoding="utf-8") as fh:
        data = json.load(fh)
    n, s = int(data["n"]), list(data["set"])
    if len(set(s)) != len(s):
        raise ValueError("duplicate elements")
    if any(not (1 <= x <= n) for x in s):
        raise ValueError("element out of range")
    members = set(s)
    for a in members:
        for b in members:
            if a + b in members:
                raise ValueError(f"not sum-free: {a}+{b}={a + b}")
    return float(len(s))
