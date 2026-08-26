from fastapi import APIRouter

from app.api.account import router as account_router
from app.api.artifact import router as artifact_router
from app.api.agent_run import router as agent_run_router
from app.api.conversation import router as conversation_router
from app.api.document import router as document_router
from app.api.evaluation import router as evaluation_router
from app.api.job_application import router as job_application_router
from app.api.workspace import router as workspace_router

api_router = APIRouter()

api_router.include_router(account_router)
api_router.include_router(artifact_router)
api_router.include_router(agent_run_router)
api_router.include_router(conversation_router)
api_router.include_router(document_router)
api_router.include_router(evaluation_router)
api_router.include_router(job_application_router)
api_router.include_router(workspace_router)
