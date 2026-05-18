"""Map simulator steps/actions to documented user-session phases."""

from __future__ import annotations

# Keys are step or action names from events.json; values cite app session walkthrough phases.
SESSION_FLOW_LABELS: dict[str, str] = {
    "place_order": "Phase 17 - Submit Order",
    "reorder_place_order": "Phase 17 - Submit Order",
    "complete_payment": "Phase 19 - Payment / Free Order Handling",
    "complete_free_order": "Phase 19 - Payment / Free Order Handling",
    "verify_completed": "Phase 20 - Order Details Fetch",
    "generate_receipt": "Phase 23 - Generate Receipt PDF",
    "submit_review": "Phase 22 - Rate The Store",
    "fetch_reorder": "Phase 24 - Reorder Sheet",
    "reorder_cart_built": "Phase 24 - Reorder Sheet",
}


def flow_label_for(*, step: str | None = None, action: str | None = None) -> str | None:
    for key in (step, action):
        if not key:
            continue
        label = SESSION_FLOW_LABELS.get(str(key).strip())
        if label:
            return label
    return None
