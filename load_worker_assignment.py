from __future__ import annotations


def build_worker_user_index_assignment(
    *,
    all_users: bool,
    worker_count: int,
    plan_user_count: int,
) -> list[int]:
    """Return deterministic plan-user indices for each load worker."""
    if worker_count < 1:
        return []

    if not all_users:
        return [0] * worker_count

    if plan_user_count < 1:
        raise ValueError("plan_user_count must be >= 1 when all_users is enabled.")

    if worker_count <= plan_user_count:
        return list(range(worker_count))

    return [index % plan_user_count for index in range(worker_count)]


def summarize_worker_user_index_counts(
    *,
    all_users: bool,
    worker_count: int,
    plan_user_count: int,
) -> dict[int, int]:
    """Return how many workers each plan-user index receives."""
    indexes = build_worker_user_index_assignment(
        all_users=all_users,
        worker_count=worker_count,
        plan_user_count=plan_user_count,
    )
    counts: dict[int, int] = {}
    for index in indexes:
        counts[index] = counts.get(index, 0) + 1
    return counts
