from core import AgentManager, FootprintReader
from core.settings import ClusterHeaders as chs


class IntraDay(FootprintReader):
    def __init__(self, manager: AgentManager) -> None:
        super().__init__(manager)
        self.temp_poc = 0

    def check_patterns(self, idy: int, idx: int) -> None:
        cv, footprint = self.convert, self.footprint
        ic = self.indicators
        # - - -
        price = cv.to_price(cv.get_nPrice(idy))
        qtyInLevel = cv.to_qty(footprint[idy, idx])
        cid = self.convert.get_cluster_id(idx)
        hr = self.headers[cid : cid + chs._HeadersCount].tolist()
        VPpocId, VPpocValue = ic.poc(), ic.poc(index=False)
        vwap, cvd = ic.vwap(), ic.cvd()
        if VPpocValue > self.temp_poc:
            self.temp_poc = VPpocValue
            print(cv.to_qty(self.temp_poc), vwap, cvd)
