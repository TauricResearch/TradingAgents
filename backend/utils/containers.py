from dependency_injector import containers, providers
from utils.database import get_session
from utils.crypto import Crypto
from member.infra.repository.member_repo import MemberRepository
from member.application.member_service import MemberService
from ulid import ULID

class Container(containers.DeclarativeContainer):
    wiring_config = containers.WiringConfiguration(
        packages=["member", "session"]
    )

    db_session = providers.Resource(get_session)
    crypto = providers.Factory(Crypto)
    ulid = providers.Factory(ULID)

    member_repo = providers.Factory(
        MemberRepository,
        session=db_session
    )

    member_service = providers.Factory(
        MemberService,
        member_repo=member_repo,
        crypto=crypto,
        db_session=db_session,
        ulid=ulid
    )

