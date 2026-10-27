"""SlotFold: honeycomb location consolidator for warehouse rack slots."""

from .model import FoldPlan, Location
from .warehouse import Warehouse
from .fold import fold

__all__ = ["FoldPlan", "Location", "Warehouse", "fold"]
__version__ = "0.1.0"
