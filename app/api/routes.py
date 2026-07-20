"""REST 接口（对应 Java AiController）。"""
from __future__ import annotations

from fastapi import APIRouter

from app.api.auth import router as auth_router
from app.api.chart_cases import router as chart_cases_router
from app.api.favorites import router as favorites_router
from app.api.admin_accounts import router as admin_accounts_router
from app.api.admin_users import router as admin_users_router
from app.api.feedback import router as feedback_router
from app.api.me import router as me_router
from app.api.observability import router as observability_router
from app.api.profiles import router as profiles_router
from app.api.rag import chat_router as rag_chat_router, mgmt_router as rag_mgmt_router
from app.api.state import set_instances
from app.api.tarot import router as tarot_router
from app.api.tarot_records import router as tarot_records_router
from app.api.tools import router as tools_router
from app.api.xianzhi import router as xianzhi_router

router = APIRouter(prefix="/ai", tags=["AI"])
router.include_router(auth_router)
router.include_router(chart_cases_router, prefix="/xianzhi")
router.include_router(xianzhi_router)
router.include_router(tarot_router)
router.include_router(rag_chat_router)
router.include_router(rag_mgmt_router)
router.include_router(tools_router)
router.include_router(observability_router)
router.include_router(profiles_router)
router.include_router(favorites_router)
router.include_router(tarot_records_router)
router.include_router(feedback_router)
router.include_router(me_router)
router.include_router(admin_users_router)
router.include_router(admin_accounts_router)