"""Greedy 3D packer: deepest-bottom-left with optional XY rotation.

Pieces are placed at candidate corners. A carton must sit on the floor or on
enough supporting area from cartons below so stacks do not float.
"""

from __future__ import annotations

from dataclasses import dataclass

from .model import BoxSpec, Container, Shipment

SUPPORT_RATIO = 0.7


@dataclass(frozen=True)
class Placement:
    sku: str
    index: int
    x: int
    y: int
    z: int
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float

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
            "sku": self.sku,
            "index": self.index,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
        }


@dataclass
class PackResult:
    container: Container
    placements: list[Placement]
    unpacked: list[dict[str, object]]
    volume_used_mm3: int
    weight_used_kg: float
    allow_rotation: bool
    this_side_up: bool

    @property
    def all_fit(self) -> bool:
        return not self.unpacked

    @property
    def volume_utilization(self) -> float:
        total = self.container.volume_mm3
        return self.volume_used_mm3 / total if total else 0.0

    @property
    def weight_utilization(self) -> float:
        total = self.container.max_weight_kg
        return self.weight_used_kg / total if total else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "container": self.container.as_dict(),
            "all_fit": self.all_fit,
            "packed_count": len(self.placements),
            "unpacked_count": sum(int(item["quantity"]) for item in self.unpacked),
            "volume_used_m3": round(self.volume_used_mm3 / 1_000_000_000, 6),
            "volume_utilization": round(self.volume_utilization, 4),
            "weight_used_kg": round(self.weight_used_kg, 3),
            "weight_utilization": round(self.weight_utilization, 4),
            "allow_rotation": self.allow_rotation,
            "this_side_up": self.this_side_up,
            "placements": [p.as_dict() for p in self.placements],
            "unpacked": self.unpacked,
        }


def pack(shipment: Shipment) -> PackResult:
    shipment.validate()
    pieces = shipment.expand()
    pieces.sort(key=lambda box: (-max(box.length_mm, box.width_mm, box.height_mm), -box.volume_mm3, -box.weight_kg))

    placements: list[Placement] = []
    candidates: list[tuple[int, int, int]] = [(0, 0, 0)]
    unpacked_pieces: list[BoxSpec] = []
    weight = 0.0
    index = 0

    for piece in pieces:
        if weight + piece.weight_kg > shipment.container.max_weight_kg + 1e-9:
            unpacked_pieces.append(piece)
            continue
        placed = _place_piece(piece, index, shipment, placements, candidates)
        if placed is None:
            unpacked_pieces.append(piece)
            continue
        placements.append(placed)
        weight += piece.weight_kg
        index += 1
        candidates = _extend_candidates(candidates, placed, shipment.container)

    volume = sum(p.length_mm * p.width_mm * p.height_mm for p in placements)
    return PackResult(
        container=shipment.container,
        placements=placements,
        unpacked=_group_unpacked(unpacked_pieces),
        volume_used_mm3=volume,
        weight_used_kg=weight,
        allow_rotation=shipment.allow_rotation,
        this_side_up=shipment.this_side_up,
    )


def _place_piece(
    piece: BoxSpec,
    index: int,
    shipment: Shipment,
    placements: list[Placement],
    candidates: list[tuple[int, int, int]],
) -> Placement | None:
    ordered = sorted(candidates, key=lambda p: (p[2], p[1], p[0]))
    for x, y, z in ordered:
        for l, w, h in _orientations(piece, shipment.allow_rotation, shipment.this_side_up):
            trial = Placement(
                sku=piece.sku,
                index=index,
                x=x,
                y=y,
                z=z,
                length_mm=l,
                width_mm=w,
                height_mm=h,
                weight_kg=piece.weight_kg,
            )
            if _fits(trial, shipment.container, placements):
                return trial
    return None


def _orientations(piece: BoxSpec, allow_rotation: bool, this_side_up: bool) -> list[tuple[int, int, int]]:
    l, w, h = piece.length_mm, piece.width_mm, piece.height_mm
    if not allow_rotation:
        return [(l, w, h)]
    if this_side_up:
        seen = []
        for dims in ((l, w, h), (w, l, h)):
            if dims not in seen:
                seen.append(dims)
        return seen
    seen = []
    for dims in (
        (l, w, h),
        (w, l, h),
        (l, h, w),
        (h, l, w),
        (w, h, l),
        (h, w, l),
    ):
        if dims not in seen:
            seen.append(dims)
    return seen


def _fits(trial: Placement, container: Container, placed: list[Placement]) -> bool:
    if trial.x2 > container.length_mm or trial.y2 > container.width_mm or trial.z2 > container.height_mm:
        return False
    if trial.x < 0 or trial.y < 0 or trial.z < 0:
        return False
    for other in placed:
        if _overlaps(trial, other):
            return False
    return _supported(trial, placed)


def _overlaps(a: Placement, b: Placement) -> bool:
    return not (a.x2 <= b.x or b.x2 <= a.x or a.y2 <= b.y or b.y2 <= a.y or a.z2 <= b.z or b.z2 <= a.z)


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
        ix = max(0, min(trial.x2, other.x2) - max(trial.x, other.x))
        iy = max(0, min(trial.y2, other.y2) - max(trial.y, other.y))
        covered += ix * iy
    return covered / base >= SUPPORT_RATIO


def _extend_candidates(
    candidates: list[tuple[int, int, int]],
    placed: Placement,
    container: Container,
) -> list[tuple[int, int, int]]:
    extra = [
        (placed.x2, placed.y, placed.z),
        (placed.x, placed.y2, placed.z),
        (placed.x, placed.y, placed.z2),
    ]
    merged: list[tuple[int, int, int]] = []
    seen: set[tuple[int, int, int]] = set()
    for point in [*candidates, *extra]:
        x, y, z = point
        if point in seen:
            continue
        if x >= container.length_mm or y >= container.width_mm or z >= container.height_mm:
            continue
        if _inside_any(x, y, z, placed):
            continue
        seen.add(point)
        merged.append(point)
    # Drop points that now sit inside the newly placed carton.
    cleaned = []
    for point in merged:
        x, y, z = point
        if placed.x <= x < placed.x2 and placed.y <= y < placed.y2 and placed.z <= z < placed.z2:
            continue
        cleaned.append(point)
    return cleaned


def _inside_any(x: int, y: int, z: int, placed: Placement) -> bool:
    return placed.x <= x < placed.x2 and placed.y <= y < placed.y2 and placed.z <= z < placed.z2


def _group_unpacked(pieces: list[BoxSpec]) -> list[dict[str, object]]:
    grouped: dict[tuple, dict[str, object]] = {}
    for piece in pieces:
        key = (piece.sku, piece.length_mm, piece.width_mm, piece.height_mm, piece.weight_kg)
        if key not in grouped:
            grouped[key] = {
                "sku": piece.sku,
                "length_mm": piece.length_mm,
                "width_mm": piece.width_mm,
                "height_mm": piece.height_mm,
                "weight_kg": piece.weight_kg,
                "quantity": 0,
                "reason": "no space or payload remaining",
            }
        grouped[key]["quantity"] = int(grouped[key]["quantity"]) + 1
    return list(grouped.values())
