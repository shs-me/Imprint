from core.utils.monitoring.agent_manager import AgentManager


class RestSimAgent:
    def __init__(self, manager: AgentManager) -> None:
        self.manager = manager

        self.cfgBT = manager.cfgBacktesting
        self.tick_size = self.cfgBT.tick_size
        self.lot_size = self.cfgBT.lot_size

    def get_tick_size(self) -> str:
        return self.tick_size

    def get_lot_size(self) -> str:
        return self.lot_size

    def send_order(self) -> bool:
        return True
