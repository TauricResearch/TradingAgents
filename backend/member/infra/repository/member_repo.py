from member.domain.repository import IMemberRepository
from sqlmodel import Session, select
from member.domain.member import Member as MemberVO
from member.infra.db_models.member import Member
from utils.db_utils import row_to_dict
from sqlalchemy import func

class MemberRepository(IMemberRepository):
    def __init__(self, session: Session):
        self.session = session

    def find_by_email(self, email: str) -> MemberVO | None:
        query = select(Member).where(Member.email == email)
        member = self.session.exec(query).first()

        if not member:
            return None
        
        return MemberVO(**row_to_dict(member))

    def save(self, member: MemberVO) -> MemberVO:
        new_member = Member(
            id=member.id,
            email=member.email,
            name=member.name,
            password=member.password,
            role=member.role,
            created_at=member.created_at,
            updated_at=member.updated_at
        )

        self.session.add(new_member)
        self.session.flush()
        self.session.refresh(new_member)

        member.id = new_member.id
        return member


    def get_members(self, page: int, items_per_page: int) -> tuple[int, list[MemberVO]]:
        offset = (page - 1) * items_per_page
        total_count_query = select(func.count(Member.id))
        total_count = self.session.exec(total_count_query).one()

        if total_count == 0:
            return 0, []

        query = (
            select(Member)
                        .order_by(Member.created_at.desc())
                        .offset(offset)
                        .limit(items_per_page)
        )

        members = self.session.exec(query).all()

        return total_count, [MemberVO(**row_to_dict(member)) for member in members]

    def find_by_id(self, id: str) -> MemberVO | None:
        query = select(Member).where(Member.id == id)
        member = self.session.exec(query).first()

        if not member:
            return None
        
        return MemberVO(**row_to_dict(member))
