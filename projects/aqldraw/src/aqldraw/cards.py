"""Screening sample-size cards for inbound QC.

These are dock-side working figures, not ISO 2859-1 / ANSI Z1.4.
Lot size picks a letter. Inspection level and severity slide that letter.
Sample size follows the letter (capped at the lot). Accept number is a
Poisson 95% screen on n × AQL / 100.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

LETTERS = ("A", "B", "C", "D", "E", "F", "G", "H", "J", "K", "L", "M", "N", "P", "Q")

SAMPLE_N: dict[str, int] = {
    "A": 2,
    "B": 3,
    "C": 5,
    "D": 8,
    "E": 13,
    "F": 20,
    "G": 32,
    "H": 50,
    "J": 80,
    "K": 125,
    "L": 200,
    "M": 315,
    "N": 500,
    "P": 800,
    "Q": 1250,
}

# Inspection level II lot-size bands (inclusive).
RANGES_II: tuple[tuple[int, int, str], ...] = (
    (2, 8, "A"),
    (9, 15, "B"),
    (16, 25, "C"),
    (26, 50, "D"),
    (51, 90, "E"),
    (91, 150, "F"),
    (151, 280, "G"),
    (281, 500, "H"),
    (501, 1200, "J"),
    (1201, 3200, "K"),
    (3201, 10000, "L"),
    (10001, 35000, "M"),
    (35001, 150000, "N"),
    (150001, 500000, "P"),
    (500001, 10**12, "Q"),
)

# Spot-check bands: much smaller samples for a walk-the-dock glance.
RANGES_S2: tuple[tuple[int, int, str], ...] = (
    (2, 25, "A"),
    (26, 90, "B"),
    (91, 500, "C"),
    (501, 3200, "D"),
    (3201, 35000, "E"),
    (35001, 10**12, "F"),
)

LEVELS: dict[str, str] = {
    "S-2": "Spot check",
    "I": "Level I (smaller sample)",
    "II": "Level II (normal)",
    "III": "Level III (tighter)",
}

LEVEL_SHIFT = {"S-2": 0, "I": -1, "II": 0, "III": 1}
SEVERITY_SHIFT = {"reduced": -1, "normal": 0, "tightened": 1}
SEVERITIES = ("reduced", "normal", "tightened")

AQL_PRESETS = (0.65, 1.0, 1.5, 2.5, 4.0, 6.5)
DEFAULT_CLASSES = {"critical": 0.65, "major": 2.5, "minor": 6.5}
CLASS_ORDER = ("critical", "major", "minor")

Z_NORMAL = 1.645  # one-sided 95% Poisson screen


@dataclass(frozen=True)
class Level:
    id: str
    name: str

    def as_dict(self) -> dict[str, object]:
        return {"id": self.id, "name": self.name}


def get_level(value: str) -> str:
    key = str(value).strip().upper().replace("S2", "S-2")
    if key in ("S-2", "I", "II", "III"):
        return key
    known = ", ".join(LEVELS)
    raise ValueError(f"Unknown inspection level '{value}'. Known: {known}")


def get_severity(value: str) -> str:
    key = str(value).strip().lower()
    if key in SEVERITY_SHIFT:
        return key
    known = ", ".join(SEVERITIES)
    raise ValueError(f"Unknown severity '{value}'. Known: {known}")


def _letter_from_ranges(lot_size: int, ranges: tuple[tuple[int, int, str], ...]) -> str:
    if lot_size <= 1:
        return "A"
    for low, high, letter in ranges:
        if low <= lot_size <= high:
            return letter
    return ranges[-1][2]


def _shift_letter(letter: str, delta: int) -> str:
    idx = LETTERS.index(letter)
    idx = max(0, min(len(LETTERS) - 1, idx + delta))
    return LETTERS[idx]


def letter_for(lot_size: int, level: str, severity: str) -> str:
    if lot_size < 1:
        raise ValueError("Lot size must be at least 1")
    level_id = get_level(level)
    sev = get_severity(severity)
    base = _letter_from_ranges(lot_size, RANGES_S2 if level_id == "S-2" else RANGES_II)
    return _shift_letter(base, LEVEL_SHIFT[level_id] + SEVERITY_SHIFT[sev])


def sample_size(letter: str, lot_size: int) -> tuple[int, bool]:
    planned = SAMPLE_N[letter]
    n = min(planned, lot_size)
    return n, n == lot_size


def accept_number(n: int, aql: float) -> int:
    """Poisson 95% screen: floor(λ + 1.645√λ), λ = n × AQL / 100.

    AQL 0 is zero-tolerance (Ac = 0). Reject number is always Ac + 1.
    """
    if n < 1:
        raise ValueError("Sample size must be at least 1")
    if aql < 0:
        raise ValueError("AQL cannot be negative")
    if aql == 0:
        return 0
    mean = n * aql / 100.0
    return int(math.floor(mean + Z_NORMAL * math.sqrt(mean) + 1e-12))


def reject_number(ac: int) -> int:
    return ac + 1


def cards_payload() -> dict[str, object]:
    letters = []
    for letter in LETTERS:
        letters.append({"id": letter, "sample_size": SAMPLE_N[letter]})
    return {
        "levels": [Level(key, name).as_dict() for key, name in LEVELS.items()],
        "severities": list(SEVERITIES),
        "aql_presets": list(AQL_PRESETS),
        "default_classes": dict(DEFAULT_CLASSES),
        "letters": letters,
        "rule": (
            "Ac = floor(n × AQL/100 + 1.645 × sqrt(n × AQL/100)); Re = Ac + 1. "
            "Screening figures, not ISO 2859-1."
        ),
    }
