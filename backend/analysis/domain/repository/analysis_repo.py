from abc import ABC, abstractmethod
from analysis.domain.analysis import Analysis as AnalysisVO

class IAnalysisRepository(ABC):
    @abstractmethod
    def find_by_member_id(self, member_id: str) -> list[AnalysisVO] | None:
        raise NotImplementedError()

    @abstractmethod
    def update(self, analysis_id: str, updates: dict) -> AnalysisVO | None:
        raise NotImplementedError()

    @abstractmethod
    def create(self, member_id: str) -> AnalysisVO:
        raise NotImplementedError()