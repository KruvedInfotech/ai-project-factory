"""Greedy pack-station cartonizer.

One order per carton. Same-temp pieces top off an open shipper before a
new one is opened. The catalog's smallest legal carton is chosen first.
Pieces that fail a check stay on the leftover board with a reason.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from .catalog import Catalog, Shipper
from .model import PackJob, Piece

SUPPORT_RATIO = 0.7


@dataclass(frozen=True)
class Placement:
    sku: str
    order_id: str
    carton_id: str
    index: int
    x: int
    y: int
    z: int
    length_mm: int
    width_mm: int
    height_mm: int
    weight_kg: float
    temp: str

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
            "order_id": self.order_id,
            "carton_id": self.carton_id,
            "index": self.index,
            "x": self.x,
            "y": self.y,
            "z": self.z,
            "length_mm": self.length_mm,
            "width_mm": self.width_mm,
            "height_mm": self.height_mm,
            "weight_kg": self.weight_kg,
            "temp": self.temp,
        }


@dataclass
class OpenCarton:
    id: str
    shipper: Shipper
    order_id: str
    temp: str
    placements: list[Placement] = field(default_factory=list)
    candidates: list[tuple[int, int, int]] = field(default_factory=lambda: [(0, 0, 0)])

    @property
    def weight_kg(self) -> float:
        return sum(p.weight_kg for p in self.placements)

    @property
    def volume_used_mm3(self) -> int:
        return sum(p.length_mm * p.width_mm * p.height_mm for p in self.placements)

    @property
    def fill(self) -> float:
        total = self.shipper.volume_mm3
        return self.volume_used_mm3 / total if total else 0.0

    def as_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "order_id": self.order_id,
            "temp": self.temp,
            "shipper": self.shipper.as_dict(),
            "piece_count": len(self.placements),
            "weight_kg": round(self.weight_kg, 3),
            "weight_utilization": round(
                self.weight_kg / self.shipper.max_weight_kg if self.shipper.max_weight_kg else 0.0,
                4,
            ),
            "volume_utilization": round(self.fill, 4),
            "placements": [p.as_dict() for p in self.placements],
        }


@dataclass
class PackResult:
    catalog: Catalog
    cartons: list[OpenCarton]
    leftover: list[dict[str, object]]
    labor_used: int
    labor_cap: int
    packed_count: int
    piece_count: int

    @property
    def all_fit(self) -> bool:
        return not self.leftover

    @property
    def carton_count(self) -> int:
        return len(self.cartons)

    @property
    def leftover_count(self) -> int:
        return sum(int(item["quantity"]) for item in self.leftover)

    @property
    def labor_utilization(self) -> float:
        return self.labor_used / self.labor_cap if self.labor_cap else 0.0

    @property
    def mean_void(self) -> float:
        if not self.cartons:
            return 0.0
        return 1.0 - (sum(c.fill for c in self.cartons) / len(self.cartons))

    def as_dict(self) -> dict[str, object]:
        return {
            "catalog": self.catalog.as_dict(),
            "all_fit": self.all_fit,
            "carton_count": self.carton_count,
            "packed_count": self.packed_count,
            "piece_count": self.piece_count,
            "leftover_count": self.leftover_count,
            "labor_used": self.labor_used,
            "labor_cap": self.labor_cap,
            "labor_utilization": round(self.labor_utilization, 4),
            "mean_void": round(self.mean_void, 4),
            "cartons": [carton.as_dict() for carton in self.cartons],
            "leftover": self.leftover,
        }


def pack(job: PackJob) -> PackResult:
    job.validate()
    pieces = job.expand()
    pieces.sort(
        key=lambda piece: (
            piece.order_id,
            -max(piece.length_mm, piece.width_mm, piece.height_mm),
            -piece.volume_mm3,
            -piece.weight_kg,
            piece.sku,
            piece.index,
        )
    )

    cartons: list[OpenCarton] = []
    leftover_pieces: list[tuple[Piece, str]] = []
    labor = 0
    seq = 0

    for piece in pieces:
        dim_ok = _catalog_fits_dims(piece, job)
        weight_ok = _catalog_fits_weight(piece, job)
        if not dim_ok:
            leftover_pieces.append((piece, "too-big"))
            continue
        if not weight_ok:
            leftover_pieces.append((piece, "too-heavy"))
            continue

        placed = _top_off(piece, cartons, job)
        if placed is not None:
            if labor + job.minutes_per_piece > job.labor_minutes:
                leftover_pieces.append((piece, "labor cap"))
                continue
            carton, placement = placed
            carton.placements.append(placement)
            carton.candidates = _extend_candidates(carton.candidates, placement, carton.shipper)
            labor += job.minutes_per_piece
            continue

        open_cost = job.minutes_per_carton + job.minutes_per_piece
        if labor + open_cost > job.labor_minutes:
            leftover_pieces.append((piece, "labor cap"))
            continue

        shipper = _smallest_empty_fit(piece, job)
        if shipper is None:
            leftover_pieces.append((piece, "too-heavy"))
            continue

        seq += 1
        carton = OpenCarton(
            id=f"BOX-{seq:03d}",
            shipper=shipper,
            order_id=piece.order_id,
            temp=piece.temp,
        )
        placement = _place_piece(piece, carton, job)
        if placement is None:
            leftover_pieces.append((piece, "too-big"))
            continue
        carton.placements.append(placement)
        carton.candidates = _extend_candidates(carton.candidates, placement, carton.shipper)
        cartons.append(carton)
        labor += open_cost

    return PackResult(
        catalog=job.catalog,
        cartons=cartons,
        leftover=_group_leftover(leftover_pieces),
        labor_used=labor,
        labor_cap=job.labor_minutes,
        packed_count=sum(len(c.placements) for c in cartons),
        piece_count=len(job.expand()),
    )


def _top_off(
    piece: Piece, cartons: list[OpenCarton], job: PackJob
) -> tuple[OpenCarton, Placement] | None:
    candidates = [
        carton
        for carton in cartons
        if carton.order_id == piece.order_id and carton.temp == piece.temp
    ]
    candidates.sort(key=lambda carton: (-carton.fill, carton.id))
    for carton in candidates:
        if carton.weight_kg + piece.weight_kg > carton.shipper.max_weight_kg + 1e-9:
            continue
        placement = _place_piece(piece, carton, job)
        if placement is not None:
            return carton, placement
    return None


def _smallest_empty_fit(piece: Piece, job: PackJob) -> Shipper | None:
    fits = []
    for shipper in job.catalog.cartons:
        if piece.weight_kg > shipper.max_weight_kg + 1e-9:
            continue
        if _orientations_fit(piece, shipper, job):
            fits.append(shipper)
    if not fits:
        return None
    return min(fits, key=lambda s: (s.volume_mm3, s.max_weight_kg, s.id))


def _catalog_fits_dims(piece: Piece, job: PackJob) -> bool:
    return any(_orientations_fit(piece, shipper, job) for shipper in job.catalog.cartons)


def _catalog_fits_weight(piece: Piece, job: PackJob) -> bool:
    return any(
        _orientations_fit(piece, shipper, job) and piece.weight_kg <= shipper.max_weight_kg + 1e-9
        for shipper in job.catalog.cartons
    )


def _orientations_fit(piece: Piece, shipper: Shipper, job: PackJob) -> bool:
    for length, width, height in _orientations(piece, job.allow_rotation, job.this_side_up):
        if length <= shipper.length_mm and width <= shipper.width_mm and height <= shipper.height_mm:
            return True
    return False


def _place_piece(piece: Piece, carton: OpenCarton, job: PackJob) -> Placement | None:
    ordered = sorted(carton.candidates, key=lambda point: (point[2], point[1], point[0]))
    for x, y, z in ordered:
        for length, width, height in _orientations(piece, job.allow_rotation, job.this_side_up):
            trial = Placement(
                sku=piece.sku,
                order_id=piece.order_id,
                carton_id=carton.id,
                index=piece.index,
                x=x,
                y=y,
                z=z,
                length_mm=length,
                width_mm=width,
                height_mm=height,
                weight_kg=piece.weight_kg,
                temp=piece.temp,
            )
            if _fits(trial, carton):
                return trial
    return None


def _orientations(piece: Piece, allow_rotation: bool, this_side_up: bool) -> list[tuple[int, int, int]]:
    length, width, height = piece.length_mm, piece.width_mm, piece.height_mm
    if not allow_rotation:
        return [(length, width, height)]
    if this_side_up:
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


def _fits(trial: Placement, carton: OpenCarton) -> bool:
    shipper = carton.shipper
    if trial.x2 > shipper.length_mm or trial.y2 > shipper.width_mm or trial.z2 > shipper.height_mm:
        return False
    if trial.x < 0 or trial.y < 0 or trial.z < 0:
        return False
    if carton.weight_kg + trial.weight_kg > shipper.max_weight_kg + 1e-9:
        return False
    for other in carton.placements:
        if _overlaps(trial, other):
            return False
    return _supported(trial, carton.placements)


def _overlaps(a: Placement, b: Placement) -> bool:
    return not (
        a.x2 <= b.x or b.x2 <= a.x or a.y2 <= b.y or b.y2 <= a.y or a.z2 <= b.z or b.z2 <= a.z
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
        ix = max(0, min(trial.x2, other.x2) - max(trial.x, other.x))
        iy = max(0, min(trial.y2, other.y2) - max(trial.y, other.y))
        covered += ix * iy
    return covered / base >= SUPPORT_RATIO


def _extend_candidates(
    candidates: list[tuple[int, int, int]],
    placed: Placement,
    shipper: Shipper,
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
        if x >= shipper.length_mm or y >= shipper.width_mm or z >= shipper.height_mm:
            continue
        if placed.x <= x < placed.x2 and placed.y <= y < placed.y2 and placed.z <= z < placed.z2:
            continue
        seen.add(point)
        merged.append(point)
    return merged


def _group_leftover(pieces: list[tuple[Piece, str]]) -> list[dict[str, object]]:
    grouped: dict[tuple, dict[str, object]] = {}
    for piece, reason in pieces:
        key = (*piece.key, reason)
        if key not in grouped:
            grouped[key] = {
                "order_id": piece.order_id,
                "sku": piece.sku,
                "length_mm": piece.length_mm,
                "width_mm": piece.width_mm,
                "height_mm": piece.height_mm,
                "weight_kg": piece.weight_kg,
                "temp": piece.temp,
                "quantity": 0,
                "reason": reason,
            }
        grouped[key]["quantity"] = int(grouped[key]["quantity"]) + 1
    leftover = list(grouped.values())
    leftover.sort(key=lambda item: (str(item["order_id"]), str(item["sku"]), str(item["reason"])))
    return leftover
