"""CrewCut: warehouse labor and shift staffing."""

from .model import Board, Associate, DemandSlot
from .staff import staff

__all__ = ["Associate", "Board", "DemandSlot", "staff"]
__version__ = "0.1.0"
