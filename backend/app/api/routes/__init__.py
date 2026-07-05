from .chat import router as chat_router
from .documents import router as documents_router
from .settings import router as settings_router

__all__ = ["chat_router", "documents_router", "settings_router"]
