"""Greedy mixed-pallet builder: store lock, heavy-first, crush on top."""

from __future__ import annotations

from dataclasses import dataclass, field

from .decks import Deck
from .model import Build, CaseSpec

SUPPORT_RATIO = 0.7


@dataclass(frozen=True)
class Placement:
    pallet_id: str
    sku: str
    store: str
    family: str
    temp: str
    index: int
    x: int
    y: int
    z: int
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    crushable: bool

    @property
    def x2(self) -> int:
        return self.x + self.length_mm

    @property
    def y2(self) -> int:
        return self.y + self.width_mm

    @property
    def z2(self) -> int:
        return self.z + self.height_mm

    def as_dict(self) -> dict[str, object]:
        return {
            "pallet_id": self.pallet_id,
            "sku": self.sku,
            "store": self.store,
            "family": self.family,
            "temp": self.temp,
            "index": self.index,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": round(self.weight_kg, 3),
            "crushable": self.crushable,
        }


@dataclass
class OpenPallet:
    index: int
    store: str
    temp: str
    placements: list[Placement] = field(default_factory=list)
    minutes: int = 0

    @property
    def id(self) -> str:
        return f"P{self.index}"

    @property
    def weight_kg(self) -> float:
        return sum(item.weight_kg for item in self.placements)

    @property
    def volume_mm3(self) -> int:
        return sum(item.length_mm * item.width_mm * item.height_mm for item in self.placements)

    def families(self) -> set[str]:
        return {item.family for item in self.placements}


@dataclass
class PackResult:
    deck: Deck
    strategy: str
    store_lock: bool
    allow_rotation: bool
    labor_cap_min: int
    labor_used_min: int
    placements: list[Placement]
    leftover: list[dict[str, object]]
    pallets: list[dict[str, object]]

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def pallet_count(self) -> int:
        return len(self.pallets)

    @property
    def packed_count(self) -> int:
        return len(self.placements)

    @property
    def leftover_count(self) -> int:
        return sum(int(item["quantity"]) for item in self.leftover)

    @property
    def volume_used_mm3(self) -> int:
        return sum(p.length_mm * p.width_mm * p.height_mm for p in self.placements)

    @property
    def weight_used_kg(self) -> float:
        return sum(p.weight_kg for p in self.placements)

    @property
    def volume_utilization(self) -> float:
        total = self.deck.volume_mm3 * max(self.pallet_count, 1)
        return self.volume_used_mm3 / total if total else 0.0

    @property
    def weight_utilization(self) -> float:
        total = self.deck.max_weight_kg * max(self.pallet_count, 1)
        return self.weight_used_kg / total if total else 0.0

    @property
    def labor_utilization(self) -> float:
        return self.labor_used_min / self.labor_cap_min if self.labor_cap_min else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "deck": self.deck.as_dict(),
            "strategy": self.strategy,
            "store_lock": self.store_lock,
            "allow_rotation": self.allow_rotation,
            "labor_cap_min": self.labor_cap_min,
            "labor_used_min": self.labor_used_min,
            "labor_utilization": round(self.labor_utilization, 4),
            "pallet_count": self.pallet_count,
            "packed_count": self.packed_count,
            "leftover_count": self.leftover_count,
            "volume_used_m3": round(self.volume_used_mm3 / 1_000_000_000, 6),
            "volume_utilization": round(self.volume_utilization, 4),
            "weight_used_kg": round(self.weight_used_kg, 3),
            "weight_utilization": round(self.weight_utilization, 4),
            "all_fit": self.all_fit,
            "placements": [item.as_dict() for item in self.placements],
            "leftover": list(self.leftover),
            "pallets": list(self.pallets),
        }


def pack(build: Build) -> PackResult:
    build.validate()
    labor_cap = build.labor_cap()
    labor_used = 0
    open_pallets: list[OpenPallet] = []
    leftover_pieces: list[tuple[CaseSpec, str]] = []
    index = 0

    for piece in _sort_pieces(build.expand(), build.strategy):
        hard = _hard_reason(piece, build)
        if hard:
            leftover_pieces.append((piece, hard))
            continue

        host, pose, why = _best_host(piece, index, open_pallets, build)
        if host is not None and pose is not None:
            if labor_used + build.deck.minutes_per_case > labor_cap:
                leftover_pieces.append((piece, "labor-cap"))
                continue
            host.placements.append(pose)
            host.minutes += build.deck.minutes_per_case
            labor_used += build.deck.minutes_per_case
            index += 1
            continue

        open_cost = build.deck.minutes_per_pallet + build.deck.minutes_per_case
        if len(open_pallets) >= build.deck.max_pallets:
            leftover_pieces.append((piece, why if why == "crush" else "pallet-cap"))
            continue
        if labor_used + open_cost > labor_cap:
            leftover_pieces.append((piece, "labor-cap"))
            continue

        opened = OpenPallet(index=len(open_pallets) + 1, store=piece.store, temp=piece.temp)
        pose = _place_piece(piece, index, opened, build)
        if pose is None:
            leftover_pieces.append((piece, "no-space"))
            continue
        opened.placements.append(pose)
        opened.minutes = open_cost
        open_pallets.append(opened)
        labor_used += open_cost
        index += 1

    placements = [item for host in open_pallets for item in host.placements]
    return PackResult(
        deck=build.deck,
        strategy=build.strategy,
        store_lock=build.store_lock,
        allow_rotation=build.allow_rotation,
        labor_cap_min=labor_cap,
        labor_used_min=labor_used,
        placements=placements,
        leftover=_group_leftover(leftover_pieces),
        pallets=_pallet_rows(open_pallets, build.deck),
    )


def _sort_pieces(pieces: list[CaseSpec], strategy: str) -> list[CaseSpec]:
    if strategy == "store":
        return sorted(pieces, key=lambda item: (item.store, item.family, item.sku))
    if strategy == "heavy":
        return sorted(pieces, key=lambda item: (-item.weight_kg, item.crushable, item.sku, item.store))
    if strategy == "compact":
        return sorted(pieces, key=lambda item: (item.volume_mm3, item.weight_kg, item.sku, item.store))
    return sorted(
        pieces,
        key=lambda item: (item.store, item.crushable, -item.weight_kg, item.family, item.sku),
    )


def _hard_reason(piece: CaseSpec, build: Build) -> str | None:
    deck = build.deck
    if not deck.accepts_temp(piece.temp):
        return "temp"
    if piece.weight_kg > deck.max_weight_kg + 1e-9:
        return "too-heavy"
    if not _any_orientation_fits_box(piece, build):
        return "too-big"
    return None


def _any_orientation_fits_box(piece: CaseSpec, build: Build) -> bool:
    deck = build.deck
    for length, width, height in _orientations(piece, build.allow_rotation):
        if length <= deck.length_mm and width <= deck.width_mm and height <= deck.height_mm:
            return True
    return False


def _best_host(
    piece: CaseSpec,
    index: int,
    hosts: list[OpenPallet],
    build: Build,
) -> tuple[OpenPallet | None, Placement | None, str]:
    blocked = "no-space"
    eligible: list[tuple[OpenPallet, Placement]] = []
    for host in hosts:
        if build.store_lock and host.store != piece.store:
            continue
        if host.temp != piece.temp:
            continue
        if host.weight_kg + piece.weight_kg > build.deck.max_weight_kg + 1e-9:
            blocked = "too-heavy"
            continue
        pose = _place_piece(piece, index, host, build)
        if pose is None:
            if _crush_only(piece, host, build):
                blocked = "crush"
            continue
        eligible.append((host, pose))
    if not eligible:
        return None, None, blocked

    def score(pair: tuple[OpenPallet, Placement]) -> tuple[int, float, int]:
        host, _pose = pair
        family_hits = sum(1 for item in host.placements if item.family == piece.family)
        return (-family_hits, -host.weight_kg, host.index)

    host, pose = min(eligible, key=score)
    return host, pose, ""


def _crush_only(piece: CaseSpec, host: OpenPallet, build: Build) -> bool:
    for x, y, z in _candidates(host.placements, build.deck):
        for length, width, height in _orientations(piece, build.allow_rotation):
            trial = Placement(
                pallet_id=host.id,
                sku=piece.sku,
                store=piece.store,
                family=piece.family,
                temp=piece.temp,
                index=0,
                x=x,
                y=y,
                z=z,
                length_mm=length,
                width_mm=width,
                height_mm=height,
                weight_kg=piece.weight_kg,
                crushable=piece.crushable,
            )
            if not _inside(trial, build.deck):
                continue
            if any(_overlaps(trial, other) for other in host.placements):
                continue
            if _supported(trial, host.placements) and _on_crushable(trial, host.placements):
                return True
    return False


def _place_piece(piece: CaseSpec, index: int, host: OpenPallet, build: Build) -> Placement | None:
    ordered = sorted(_candidates(host.placements, build.deck), key=lambda point: (point[2], point[1], point[0]))
    for x, y, z in ordered:
        for length, width, height in _orientations(piece, build.allow_rotation):
            trial = Placement(
                pallet_id=host.id,
                sku=piece.sku,
                store=piece.store,
                family=piece.family,
                temp=piece.temp,
                index=index,
                x=x,
                y=y,
                z=z,
                length_mm=length,
                width_mm=width,
                height_mm=height,
                weight_kg=piece.weight_kg,
                crushable=piece.crushable,
            )
            if _fits(trial, build.deck, host.placements):
                return trial
    return None


def _orientations(piece: CaseSpec, allow_rotation: bool) -> list[tuple[int, int, int]]:
    length, width, height = piece.length_mm, piece.width_mm, piece.height_mm
    if not allow_rotation:
        return [(length, width, height)]
    if piece.this_side_up:
        seen: list[tuple[int, int, int]] = []
        for dims in ((length, width, height), (width, length, height)):
            if dims not in seen:
                seen.append(dims)
        return seen
    seen = []
    for dims in (
        (length, width, height),
        (width, length, height),
        (length, height, width),
        (height, length, width),
        (width, height, length),
        (height, width, length),
    ):
        if dims not in seen:
            seen.append(dims)
    return seen


def _fits(trial: Placement, deck: Deck, placed: list[Placement]) -> bool:
    if not _inside(trial, deck):
        return False
    if any(_overlaps(trial, other) for other in placed):
        return False
    if _on_crushable(trial, placed):
        return False
    return _supported(trial, placed)


def _inside(trial: Placement, deck: Deck) -> bool:
    return (
        trial.x >= 0
        and trial.y >= 0
        and trial.z >= 0
        and trial.x2 <= deck.length_mm
        and trial.y2 <= deck.width_mm
        and trial.z2 <= deck.height_mm
    )


def _overlaps(left: Placement, right: Placement) -> bool:
    return not (
        left.x2 <= right.x
        or right.x2 <= left.x
        or left.y2 <= right.y
        or right.y2 <= left.y
        or left.z2 <= right.z
        or right.z2 <= left.z
    )


def _supported(trial: Placement, placed: list[Placement]) -> bool:
    if trial.z == 0:
        return True
    base = trial.length_mm * trial.width_mm
    if base <= 0:
        return False
    covered = 0
    for other in placed:
        if other.z2 != trial.z:
            continue
        overlap_x = max(0, min(trial.x2, other.x2) - max(trial.x, other.x))
        overlap_y = max(0, min(trial.y2, other.y2) - max(trial.y, other.y))
        covered += overlap_x * overlap_y
    return covered / base >= SUPPORT_RATIO


def _on_crushable(trial: Placement, placed: list[Placement]) -> bool:
    if trial.z == 0:
        return False
    for other in placed:
        if not other.crushable or other.z2 != trial.z:
            continue
        overlap_x = max(0, min(trial.x2, other.x2) - max(trial.x, other.x))
        overlap_y = max(0, min(trial.y2, other.y2) - max(trial.y, other.y))
        if overlap_x > 0 and overlap_y > 0:
            return True
    return False


def _candidates(placed: list[Placement], deck: Deck) -> list[tuple[int, int, int]]:
    points: list[tuple[int, int, int]] = [(0, 0, 0)]
    for item in placed:
        points.extend(
            (
                (item.x2, item.y, item.z),
                (item.x, item.y2, item.z),
                (item.x, item.y, item.z2),
            )
        )
    cleaned: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for point in points:
        if point in seen:
            continue
        x, y, z = point
        if x >= deck.length_mm or y >= deck.width_mm or z >= deck.height_mm:
            continue
        if any(item.x <= x < item.x2 and item.y <= y < item.y2 and item.z <= z < item.z2 for item in placed):
            continue
        seen.add(point)
        cleaned.append(point)
    return cleaned


def _group_leftover(pieces: list[tuple[CaseSpec, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple, dict[str, object]] = {}
    for piece, reason in pieces:
        key = (
            piece.sku,
            piece.store,
            piece.family,
            piece.temp,
            piece.length_mm,
            piece.width_mm,
            piece.height_mm,
            piece.weight_kg,
            piece.crushable,
            reason,
        )
        if key not in grouped:
            grouped[key] = {
                "sku": piece.sku,
                "store": piece.store,
                "family": piece.family,
                "temp": piece.temp,
                "length_mm": piece.length_mm,
                "width_mm": piece.width_mm,
                "height_mm": piece.height_mm,
                "weight_kg": round(piece.weight_kg, 3),
                "crushable": piece.crushable,
                "quantity": 0,
                "reason": reason,
            }
        grouped[key]["quantity"] = int(grouped[key]["quantity"]) + 1
    return list(grouped.values())


def _pallet_rows(hosts: list[OpenPallet], deck: Deck) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for host in hosts:
        height = max((item.z2 for item in host.placements), default=0)
        rows.append(
            {
                "id": host.id,
                "store": host.store,
                "temp": host.temp,
                "case_count": len(host.placements),
                "weight_kg": round(host.weight_kg, 3),
                "volume_l": round(host.volume_mm3 / 1_000_000, 4),
                "height_mm": height,
                "weight_fill": round(host.weight_kg / deck.max_weight_kg, 4) if deck.max_weight_kg else 0.0,
                "cube_fill": round(host.volume_mm3 / deck.volume_mm3, 4) if deck.volume_mm3 else 0.0,
                "minutes": host.minutes,
                "families": sorted(host.families()),
            }
        )
    return rows
