"""SlotRank: velocity-based warehouse slotting for pick faces."""

from .model import Location, SlotPlan, Sku
from .slot import slot

__all__ = ["Location", "SlotPlan", "Sku", "slot"]
__version__ = "0.1.0"
