from api.routers.auth import router as auth_router
from api.routers.projects import router as projects_router
from api.routers.jobs import router as jobs_router
from api.routers.health import router as health_router
from api.routers.upload import router as upload_router

__all__ = ["auth_router", "projects_router", "jobs_router", "health_router", "upload_router"]

from api.routers.profiles import router as profiles_router
from api.routers.analytics import router as analytics_router
from api.routers.users import router as users_router
