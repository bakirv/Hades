"""Tiny, dependency-free numerics for the AI Committee.

The committee is deliberately built on transparent linear-logistic models, so the
maths it needs is small: a numerically-safe sigmoid, clamping, a handful of
robust summary statistics, and the classification metrics the Model Monitor and
Validation Engine report. Keeping this pure-Python (no numpy/scikit) means the
brain runs anywhere — including the low-power VPS where numpy-2 aborts — and
every computation stays legible and auditable.
"""

from __future__ import annotations

import math
from collections.abc import Iterable, Sequence

_EPS = 1e-12


def clamp(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clamp ``value`` into ``[lo, hi]``."""
    return lo if value < lo else hi if value > hi else value


def sigmoid(z: float) -> float:
    """Numerically stable logistic function, always in (0, 1)."""
    if z >= 0.0:
        ez = math.exp(-min(z, 60.0))
        return 1.0 / (1.0 + ez)
    ez = math.exp(max(z, -60.0))
    return ez / (1.0 + ez)


def logit(p: float) -> float:
    """Inverse sigmoid; ``p`` is clamped away from 0/1 for safety."""
    p = clamp(p, _EPS, 1.0 - _EPS)
    return math.log(p / (1.0 - p))


def mean(values: Iterable[float]) -> float:
    items = list(values)
    return sum(items) / len(items) if items else 0.0


def stddev(values: Iterable[float]) -> float:
    items = list(values)
    if len(items) < 2:
        return 0.0
    mu = mean(items)
    var = sum((x - mu) ** 2 for x in items) / (len(items) - 1)
    return math.sqrt(max(var, 0.0))


def weighted_mean(pairs: Iterable[tuple[float, float]]) -> float:
    """Mean of ``(value, weight)`` pairs; falls back to 0 with no weight."""
    total_w = 0.0
    acc = 0.0
    for value, weight in pairs:
        acc += value * weight
        total_w += weight
    return acc / total_w if total_w > _EPS else 0.0


def entropy_norm(distribution: Sequence[float]) -> float:
    """Shannon entropy of a distribution, normalised to [0, 1].

    1.0 = maximally spread (no agreement), 0.0 = a single spike (full agreement).
    Used to turn the regime soft-scores and member spread into a stability read.
    """
    total = sum(max(0.0, x) for x in distribution)
    if total <= _EPS or len(distribution) <= 1:
        return 0.0
    h = 0.0
    for x in distribution:
        p = max(0.0, x) / total
        if p > _EPS:
            h -= p * math.log(p)
    return clamp(h / math.log(len(distribution)))


def brier_score(pairs: Sequence[tuple[float, int]]) -> float:
    """Mean squared error between predicted probability and 0/1 outcome."""
    if not pairs:
        return 0.0
    return sum((p - y) ** 2 for p, y in pairs) / len(pairs)


def log_loss(pairs: Sequence[tuple[float, int]]) -> float:
    """Binary cross-entropy; probabilities clamped away from 0/1."""
    if not pairs:
        return 0.0
    acc = 0.0
    for p, y in pairs:
        pc = clamp(p, _EPS, 1.0 - _EPS)
        acc += -(y * math.log(pc) + (1 - y) * math.log(1.0 - pc))
    return acc / len(pairs)


def accuracy(pairs: Sequence[tuple[float, int]], threshold: float = 0.5) -> float:
    if not pairs:
        return 0.0
    correct = sum(1 for p, y in pairs if (p >= threshold) == bool(y))
    return correct / len(pairs)


def precision_recall(
    pairs: Sequence[tuple[float, int]], threshold: float = 0.5
) -> tuple[float, float]:
    tp = fp = fn = 0
    for p, y in pairs:
        predicted = p >= threshold
        if predicted and y:
            tp += 1
        elif predicted and not y:
            fp += 1
        elif not predicted and y:
            fn += 1
    precision = tp / (tp + fp) if (tp + fp) else 0.0
    recall = tp / (tp + fn) if (tp + fn) else 0.0
    return precision, recall


def roc_auc(pairs: Sequence[tuple[float, int]]) -> float:
    """Rank-based ROC AUC (Mann-Whitney U). 0.5 == no discrimination.

    O(n log n) via ranking; ties get average ranks. Returns 0.5 when a class is
    absent (undefined AUC — report "no discrimination" rather than crash).
    """
    positives = [p for p, y in pairs if y]
    negatives = [p for p, y in pairs if not y]
    n_pos, n_neg = len(positives), len(negatives)
    if n_pos == 0 or n_neg == 0:
        return 0.5
    ranked = sorted(((p, y) for p, y in pairs), key=lambda t: t[0])
    ranks: list[float] = [0.0] * len(ranked)
    i = 0
    while i < len(ranked):
        j = i
        while j + 1 < len(ranked) and ranked[j + 1][0] == ranked[i][0]:
            j += 1
        avg_rank = (i + j) / 2.0 + 1.0  # ranks are 1-based
        for k in range(i, j + 1):
            ranks[k] = avg_rank
        i = j + 1
    sum_pos_ranks = sum(r for r, (_, y) in zip(ranks, ranked, strict=True) if y)
    u = sum_pos_ranks - n_pos * (n_pos + 1) / 2.0
    return clamp(u / (n_pos * n_neg))


def calibration_error(pairs: Sequence[tuple[float, int]], bins: int = 10) -> float:
    """Expected Calibration Error over equal-width probability bins."""
    if not pairs:
        return 0.0
    buckets: list[list[tuple[float, int]]] = [[] for _ in range(bins)]
    for p, y in pairs:
        idx = min(bins - 1, int(clamp(p) * bins))
        buckets[idx].append((p, y))
    total = len(pairs)
    ece = 0.0
    for bucket in buckets:
        if not bucket:
            continue
        conf = mean(p for p, _ in bucket)
        acc = mean(float(y) for _, y in bucket)
        ece += (len(bucket) / total) * abs(conf - acc)
    return ece
