from typing import List, Dict, Tuple


# CTI-9 item ranges: (min, max) for each item
# Items 1-7: 1-5 (Never to Very often)
# Item 8: 1-8 (never to very frequently)
# Item 9: 1-5 (very sad to very happy)
CTI9_ITEM_RANGES = [
    (1, 5),  # Item 1
    (1, 5),  # Item 2
    (1, 5),  # Item 3
    (1, 5),  # Item 4
    (1, 5),  # Item 5
    (1, 5),  # Item 6
    (1, 5),  # Item 7
    (1, 8),  # Item 8
    (1, 5),  # Item 9
]

# CTI-9 thresholds from validation data
# >= threshold -> "high chills" classification
CTI9_THRESHOLDS = {
    34: {"keep_pct": 34, "chills_pct": 71},
    38: {"keep_pct": 18, "chills_pct": 76},
    40: {"keep_pct": 13, "chills_pct": 81},
    42: {"keep_pct": 7, "chills_pct": 86},
}
CTI9_DEFAULT_THRESHOLD = 38

# Schema domains and their item counts
SCHEMA_DOMAINS = ["failure", "defectiveness", "dependence"]
SCHEMA_ITEMS_PER_DOMAIN = 5
# YSQ standard scale: 1-6
# 1 = Completely untrue of me
# 2 = Mostly untrue of me
# 3 = Slightly more true than untrue
# 4 = Moderately true of me
# 5 = Mostly true of me
# 6 = Describes me perfectly
SCHEMA_ITEM_MIN = 1
SCHEMA_ITEM_MAX = 6


def validate_cti9(responses: List[int]) -> Tuple[bool, str]:
    """
    Validate CTI-9 responses.
    Returns (is_valid, error_message).
    """
    if len(responses) != 9:
        return False, f"CTI-9 requires exactly 9 responses, got {len(responses)}"

    for i, (val, (lo, hi)) in enumerate(zip(responses, CTI9_ITEM_RANGES)):
        if not isinstance(val, int):
            return False, f"Item {i + 1} must be an integer, got {type(val).__name__}"
        if val < lo or val > hi:
            return False, f"Item {i + 1} must be between {lo} and {hi}, got {val}"

    return True, ""


def score_cti9(responses: List[int]) -> Dict:
    """
    Score the Chills Triage Instrument (CTI-9).

    Returns dict with:
        total: sum of all 9 items (range 9-48)
        classification: "high" or "low" based on default threshold
        threshold_used: the threshold value used
        items: the raw responses
    """
    valid, err = validate_cti9(responses)
    if not valid:
        raise ValueError(err)

    total = sum(responses)
    classification = "high" if total >= CTI9_DEFAULT_THRESHOLD else "low"

    return {
        "total": total,
        "classification": classification,
        "threshold_used": CTI9_DEFAULT_THRESHOLD,
        "items": responses,
    }


def validate_schema(responses: Dict[str, List[int]]) -> Tuple[bool, str]:
    """
    Validate schema questionnaire responses.
    Returns (is_valid, error_message).
    """
    for domain in SCHEMA_DOMAINS:
        if domain not in responses:
            return False, f"Missing schema domain: {domain}"
        items = responses[domain]
        if len(items) != SCHEMA_ITEMS_PER_DOMAIN:
            return False, f"Domain '{domain}' requires {SCHEMA_ITEMS_PER_DOMAIN} items, got {len(items)}"
        for i, val in enumerate(items):
            if not isinstance(val, (int, float)):
                return False, f"Domain '{domain}' item {i + 1} must be a number"
            if val < SCHEMA_ITEM_MIN or val > SCHEMA_ITEM_MAX:
                return False, f"Domain '{domain}' item {i + 1} must be between {SCHEMA_ITEM_MIN} and {SCHEMA_ITEM_MAX}, got {val}"

    return True, ""


def score_schema(responses: Dict[str, List[int]]) -> Dict:
    """
    Score schema questionnaire across 3 domains.
    Each domain has 5 items on a 1-6 scale.

    Returns dict with:
        domain_scores: average score per domain
        dominant_schema: the highest-scoring domain name
        domain_totals: raw sum per domain
        items: the raw responses
    """
    valid, err = validate_schema(responses)
    if not valid:
        raise ValueError(err)

    domain_scores = {}
    domain_totals = {}
    for domain in SCHEMA_DOMAINS:
        items = responses[domain]
        domain_totals[domain] = sum(items)
        domain_scores[domain] = round(sum(items) / len(items), 2)

    # Dominant schema is the highest average
    # Tie-breaking: failure > defectiveness > dependence (order in SCHEMA_DOMAINS)
    max_score = max(domain_scores.values())
    dominant = None
    for domain in SCHEMA_DOMAINS:
        if domain_scores[domain] == max_score:
            dominant = domain
            break

    return {
        "domain_scores": domain_scores,
        "domain_totals": domain_totals,
        "dominant_schema": dominant,
        "items": responses,
    }


# Schema domain labels for prompt and display
SCHEMA_LABELS = {
    "failure": "Failure",
    "defectiveness": "Defectiveness / Shame",
    "dependence": "Dependence / Incompetence",
}

# Schema domain descriptions for the speech prompt
SCHEMA_DESCRIPTIONS = {
    "failure": "This person carries a deep belief that they are inadequate, incompetent, or failing compared to others. Their core wound is around achievement, capability, and never being good enough.",
    "defectiveness": "This person carries a deep belief that they are fundamentally flawed, unlovable, or shameful. Their core wound is around being seen, accepted, and worthy of love.",
    "dependence": "This person carries a deep belief that they cannot cope on their own, that they lack the ability to handle everyday life. Their core wound is around autonomy, competence, and trusting their own judgment.",
}