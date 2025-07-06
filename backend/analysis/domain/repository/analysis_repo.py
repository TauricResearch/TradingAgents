from abc import ABC, abstractmethod
from analysis.domain.analysis import Analysis as AnalysisVO
from analysis.interface.dto import TradingAnalysisRequest

class IAnalysisRepository(ABC):
    @abstractmethod
    def find_by_member_id(self, member_id: str) -> list[AnalysisVO] | None:
        raise NotImplementedError()

    @abstractmethod
    def find_by_id(self, analysis_id: str) -> AnalysisVO | None:
        raise NotImplementedError()

    @abstractmethod
    def update(self, analysis: AnalysisVO) -> AnalysisVO | None:
        raise NotImplementedError()

    @abstractmethod
    def save(self, analysis: AnalysisVO) -> AnalysisVO:
        raise NotImplementedError()