from core.utils.monitoring.agent_manager import AgentManager


class RestEngine:
    def __init__(self, manager: AgentManager) -> None:
        self.manager = manager

    def get_tick_size(self) -> str:
        return ""

    def get_lot_size(self) -> str:
        return ""

    def send_order(self) -> bool:
        return True
