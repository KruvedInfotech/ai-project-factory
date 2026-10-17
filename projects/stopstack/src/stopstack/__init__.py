"""StopStack: multi-stop LIFO trailer loading for milk-run deliveries."""

from .model import Load, PalletLine, Stop
from .stack import stack

__all__ = ["Load", "PalletLine", "Stop", "stack"]
__version__ = "0.1.0"
