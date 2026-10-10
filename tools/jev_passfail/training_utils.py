"""Deterministic global batches for synchronous data-parallel training."""
from __future__ import annotations

import random
from collections.abc import Iterator


def epoch_batches(
    size: int,
    world_size: int,
    global_batch_size: int,
    seed: int,
    epoch: int,
) -> Iterator[tuple[list[int], list[list[int]]]]:
    if size <= 0 or world_size <= 0 or global_batch_size <= 0:
        raise ValueError("dataset and batch dimensions must be positive")
    if global_batch_size % world_size:
        raise ValueError("global batch size must be divisible by world size")
    indices = list(range(size))
    random.Random(seed + epoch).shuffle(indices)
    for start in range(0, size, global_batch_size):
        actual = indices[start : start + global_batch_size]
        padded = actual + [-1] * ((-len(actual)) % world_size)
        per_rank = [padded[rank::world_size] for rank in range(world_size)]
        if len({len(batch) for batch in per_rank}) != 1:
            raise AssertionError("DDP ranks must receive the same number of samples")
        yield actual, per_rank
