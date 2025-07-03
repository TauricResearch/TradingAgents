from sqlmodel import Session
from utils.crypto import Crypto
from member.domain.repository.member_repo import IMemberRepository
from utils.auth import Role
from member.domain.member import Member as MemberVO
from fastapi import HTTPException, status
from datetime import datetime

from ulid import ULID

class MemberService:
    def __init__(
        self,
        member_repo: IMemberRepository,
        crypto: Crypto,
        db_session: Session,
        ulid: ULID
    ):
        self.member_repo = member_repo
        self.crypto = crypto
        self.db_session = db_session
        self.ulid = ulid

    def create_member(
        self,
        name: str,
        email: str,
        password: str,
        role: Role
    ):
        try:
            if self.member_repo.find_by_email(email):
                raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Email already exists")
        except Exception as e:
            self.db_session.rollback()
            raise e

        now = datetime.now()
        member_vo = MemberVO(
            id=self.ulid.generate(),
            name=name,
            email=email,
            password=self.crypto.encrypt(password),
            created_at=now,
            updated_at=now,
            role=role
        )

        saved_member = self.member_repo.save(member_vo)
        self.db_session.commit()

        return saved_member


    def get_members(
        self,
        page: int,
        items_per_page: int
    )->tuple[int, list[MemberVO]] :
        return self.member_repo.get_members(page, items_per_page)

    def get_member(
        self,
        id: str
    )->MemberVO | None:
        member = self.member_repo.find_by_id(id)
        if not member:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Member not found")
        return member