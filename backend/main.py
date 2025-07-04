from fastapi import FastAPI
from utils.database import create_db_and_tables
from utils.containers import Container


from analysis.interface.controller.analysis_controller import router as analysis_router
from member.interface.controller.member_controller import router as member_router



app = FastAPI()
app.container = Container()

app.include_router(analysis_router)
app.include_router(member_router)


@app.on_event("startup")
def startup_db_client():
    create_db_and_tables()