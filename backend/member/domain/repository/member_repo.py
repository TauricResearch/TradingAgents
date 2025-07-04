from abc import ABC, abstractmethod
from member.domain.member import Member as MemberVO
from analysis.domain.analysis import Analysis as AnalysisVO

class IMemberRepository(ABC):
    @abstractmethod
    def find_by_email(self, email: str) -> MemberVO | None:
        raise NotImplementedError()

    @abstractmethod
    def save(self, member: MemberVO) -> MemberVO:
        raise NotImplementedError()

    @abstractmethod
    def find_by_id(self, id: str) -> MemberVO | None:
        raise NotImplementedError()

    @abstractmethod
    def get_members(self, page: int, items_per_page: int) -> tuple[int, list[MemberVO]]:
        raise NotImplementedError()

    @abstractmethod
    def find_analysis_sessions_by_member(self, member_id: str) -> list[AnalysisVO]:
        raise NotImplementedError()