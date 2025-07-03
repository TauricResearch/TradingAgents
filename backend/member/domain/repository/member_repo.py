from abc import ABC, abstractmethod
from member.domain.member import Member as MemberVO

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

