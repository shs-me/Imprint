"""Type alias declarations and exported interfaces for external strategy development."""

from ..core.engine.base.base_sync import Sync
from ..core.utils.monitoring.agent_manager import AgentManager

__all__ = [
    "Sync",
    "AgentManager",
]
