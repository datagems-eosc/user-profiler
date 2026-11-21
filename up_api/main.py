from contextlib import asynccontextmanager
import logging
import os

from fastapi import Depends, FastAPI
from fastapi.responses import RedirectResponse

from .resources import security
from .resources.graph_helpers import init_db, close_db
from .routers import dev, keywords, user

# configuring the logger to track the refresh process 
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")


@asynccontextmanager
async def lifespan(_: FastAPI):
    init_db()
    yield
    close_db()


app = FastAPI(
    title="User Profiler API",
    version="1.0.0",
    openapi_url="/api/v1/openapi.json",
    docs_url="/api/v1/swagger",
    redoc_url="/api/v1/redoc",
    root_path=os.getenv("ROOT_PATH", ""),
    lifespan=lifespan,
)


@app.get("/", include_in_schema=False)
async def home():
    return RedirectResponse(url="/api/v1")


@app.get("/api/v1")
async def api_home():
    return {"message": "User Profiler API V1 is running"}


# Every route on these routers requires a bearer token with this API in its audience
protected = [Depends(security.require_app_scope)]

# The order matters: /user/me/... must be registered before /user/{user_id}/...
#   - queries before user: GET /user/me/keywords vs GET /user/{user_id}/keywords
#   - user before dev:     POST /user/me vs POST /user/{user_id}
app.include_router(keywords.router, dependencies=protected)
app.include_router(user.router, dependencies=protected)
app.include_router(dev.router, dependencies=protected)
app.include_router(security.router, prefix="/api/v1")
