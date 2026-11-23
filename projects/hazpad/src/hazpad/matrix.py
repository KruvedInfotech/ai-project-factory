"""IMDG-inspired mixing codes for a warehouse / trailer screen.

This is a dock-side lookup, not a certified copy of IMDG 7.2 or 49 CFR 177.848.
Codes:

- C  compatible — adjacent bays are fine
- A  away from — leave `away_bays` empty between the two lots
- S  separated — solid partition (other compartment, or an empty bay)
- X  forbidden — cannot share the same pad / trailer
"""

from __future__ import annotations

from dataclasses import dataclass

CLASSES: tuple[str, ...] = (
    "2.1",
    "2.2",
    "2.3",
    "3",
    "4.1",
    "4.2",
    "4.3",
    "5.1",
    "5.2",
    "6.1",
    "8",
    "9",
    "FOOD",
)

CLASS_NAMES: dict[str, str] = {
    "2.1": "Flammable gas",
    "2.2": "Non-flammable gas",
    "2.3": "Toxic gas",
    "3": "Flammable liquid",
    "4.1": "Flammable solid",
    "4.2": "Spontaneous combustion",
    "4.3": "Dangerous when wet",
    "5.1": "Oxidizer",
    "5.2": "Organic peroxide",
    "6.1": "Toxic",
    "8": "Corrosive",
    "9": "Miscellaneous",
    "FOOD": "Foodstuffs / produce",
}

CODE_RANK = {"C": 0, "A": 1, "S": 2, "X": 3}
CODE_NAMES = {
    "C": "compatible",
    "A": "away from",
    "S": "separated",
    "X": "forbidden",
}

# Limited-quantity packages of these classes may ease X→S and S→A.
LQ_EASE_CLASSES = frozenset({"3", "4.1", "5.1", "6.1", "8", "9"})

# Same-class default is C except oxidizers (intensify) and organic peroxides.
_SAME: dict[str, str] = {
    "5.1": "A",
    "5.2": "S",
}

# Upper-triangle cross codes. Missing pairs default to C.
_CROSS: dict[tuple[str, str], str] = {
    ("2.1", "2.2"): "C",
    ("2.1", "2.3"): "S",
    ("2.1", "3"): "A",
    ("2.1", "4.1"): "A",
    ("2.1", "4.2"): "S",
    ("2.1", "4.3"): "S",
    ("2.1", "5.1"): "X",
    ("2.1", "5.2"): "X",
    ("2.1", "6.1"): "A",
    ("2.1", "8"): "A",
    ("2.1", "9"): "C",
    ("2.1", "FOOD"): "A",
    ("2.2", "2.3"): "A",
    ("2.2", "3"): "C",
    ("2.2", "4.1"): "C",
    ("2.2", "4.2"): "A",
    ("2.2", "4.3"): "A",
    ("2.2", "5.1"): "A",
    ("2.2", "5.2"): "S",
    ("2.2", "6.1"): "C",
    ("2.2", "8"): "C",
    ("2.2", "9"): "C",
    ("2.2", "FOOD"): "C",
    ("2.3", "3"): "S",
    ("2.3", "4.1"): "S",
    ("2.3", "4.2"): "X",
    ("2.3", "4.3"): "S",
    ("2.3", "5.1"): "X",
    ("2.3", "5.2"): "X",
    ("2.3", "6.1"): "S",
    ("2.3", "8"): "S",
    ("2.3", "9"): "A",
    ("2.3", "FOOD"): "X",
    ("3", "4.1"): "C",
    ("3", "4.2"): "S",
    ("3", "4.3"): "A",
    ("3", "5.1"): "X",
    ("3", "5.2"): "X",
    ("3", "6.1"): "A",
    ("3", "8"): "A",
    ("3", "9"): "C",
    ("3", "FOOD"): "A",
    ("4.1", "4.2"): "S",
    ("4.1", "4.3"): "A",
    ("4.1", "5.1"): "S",
    ("4.1", "5.2"): "X",
    ("4.1", "6.1"): "A",
    ("4.1", "8"): "A",
    ("4.1", "9"): "C",
    ("4.1", "FOOD"): "A",
    ("4.2", "4.3"): "S",
    ("4.2", "5.1"): "X",
    ("4.2", "5.2"): "X",
    ("4.2", "6.1"): "S",
    ("4.2", "8"): "S",
    ("4.2", "9"): "A",
    ("4.2", "FOOD"): "S",
    ("4.3", "5.1"): "X",
    ("4.3", "5.2"): "X",
    ("4.3", "6.1"): "S",
    ("4.3", "8"): "X",
    ("4.3", "9"): "A",
    ("4.3", "FOOD"): "S",
    ("5.1", "5.2"): "X",
    ("5.1", "6.1"): "S",
    ("5.1", "8"): "S",
    ("5.1", "9"): "A",
    ("5.1", "FOOD"): "A",
    ("5.2", "6.1"): "X",
    ("5.2", "8"): "X",
    ("5.2", "9"): "S",
    ("5.2", "FOOD"): "X",
    ("6.1", "8"): "A",
    ("6.1", "9"): "C",
    ("6.1", "FOOD"): "X",
    ("8", "9"): "C",
    ("8", "FOOD"): "X",
    ("9", "FOOD"): "C",
}

UN_PRESETS: dict[str, dict[str, str]] = {
    "1203": {"class": "3", "description": "Gasoline"},
    "1263": {"class": "3", "description": "Paint"},
    "1760": {"class": "8", "description": "Corrosive liquid n.o.s."},
    "1824": {"class": "8", "description": "Sodium hydroxide solution"},
    "1950": {"class": "2.1", "description": "Aerosols, flammable"},
    "1977": {"class": "2.2", "description": "Nitrogen, refrigerated liquid"},
    "1993": {"class": "3", "description": "Flammable liquid n.o.s."},
    "2014": {"class": "5.1", "description": "Hydrogen peroxide 20–60%"},
    "2794": {"class": "8", "description": "Batteries, wet, filled with acid"},
    "2810": {"class": "6.1", "description": "Toxic liquid, organic n.o.s."},
    "3077": {"class": "9", "description": "Environmentally hazardous solid"},
    "3101": {"class": "5.2", "description": "Organic peroxide type B, liquid"},
    "1402": {"class": "4.3", "description": "Calcium carbide"},
    "1361": {"class": "4.2", "description": "Carbon, animal or vegetable origin"},
    "1869": {"class": "4.1", "description": "Magnesium"},
    "3480": {"class": "9", "description": "Lithium ion batteries"},
    "FOOD": {"class": "FOOD", "description": "Foodstuffs / produce"},
}


def normalize_class(value: str) -> str:
    key = value.strip().upper()
    if key == "FOOD":
        return "FOOD"
    # Accept "class 3" / "3" / "2.1".
    key = key.replace("CLASS", "").strip()
    if key not in CLASSES:
        known = ", ".join(CLASSES)
        raise ValueError(f"Unknown hazard class '{value}'. Known: {known}")
    return key


def worse(a: str, b: str) -> str:
    return a if CODE_RANK[a] >= CODE_RANK[b] else b


def lookup(class_a: str, class_b: str) -> str:
    a = normalize_class(class_a)
    b = normalize_class(class_b)
    if a == b:
        return _SAME.get(a, "C")
    pair = (a, b) if CLASSES.index(a) < CLASSES.index(b) else (b, a)
    return _CROSS.get(pair, "C")


def ease_code(code: str, class_a: str, class_b: str, both_limited: bool) -> str:
    if not both_limited:
        return code
    if class_a not in LQ_EASE_CLASSES or class_b not in LQ_EASE_CLASSES:
        return code
    if code == "X":
        return "S"
    if code == "S":
        return "A"
    return code


@dataclass(frozen=True)
class MixCode:
    raw: str
    code: str
    eased: bool

    @property
    def name(self) -> str:
        return CODE_NAMES[self.code]


def mix(class_a: str, class_b: str, both_limited: bool = False) -> MixCode:
    raw = lookup(class_a, class_b)
    code = ease_code(raw, normalize_class(class_a), normalize_class(class_b), both_limited)
    return MixCode(raw=raw, code=code, eased=code != raw)


def matrix_grid() -> list[list[str]]:
    header = [""] + list(CLASSES)
    rows = [header]
    for row_cls in CLASSES:
        rows.append([row_cls] + [lookup(row_cls, col) for col in CLASSES])
    return rows


def classes_payload() -> dict[str, object]:
    return {
        "classes": [{"id": key, "name": CLASS_NAMES[key]} for key in CLASSES],
        "codes": [{"id": key, "name": name} for key, name in CODE_NAMES.items()],
        "lq_ease_classes": sorted(LQ_EASE_CLASSES),
        "matrix": matrix_grid(),
        "un_presets": [
            {"un": key, **value} for key, value in sorted(UN_PRESETS.items(), key=lambda item: item[0])
        ],
        "rule": (
            "C = adjacent OK. A = leave empty bays between. "
            "S = partition (other compartment or empty bay). X = other trailer. "
            "Limited-quantity 3 / 4.1 / 5.1 / 6.1 / 8 / 9 eases X→S and S→A."
        ),
    }
