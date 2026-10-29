"""FastAPI application: mounts all routers under /api, media at root."""

from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI

from app import storage
from app.config import settings
from app.routers import (auth, cooklog, export, favorite, health,
			 importer, media, notes, pantry, photos, recipes,
			 share, shopping, taxonomy, todo)

API_PREFIX = "/api"
DOCS_URL = API_PREFIX + "/docs"
OPENAPI_URL = API_PREFIX + "/openapi.json"


@asynccontextmanager
async def lifespan(app: FastAPI):
	if hasattr(storage, "ensure_dir"):
		storage.ensure_dir()
	yield


app = FastAPI(
	title=settings.app_name,
	docs_url=DOCS_URL if settings.api_docs else None,
	redoc_url=None,
	openapi_url=OPENAPI_URL if settings.api_docs else None,
	lifespan=lifespan,
)

api = APIRouter(prefix=API_PREFIX)
api.include_router(health.router)
api.include_router(auth.router)
api.include_router(recipes.router)
api.include_router(taxonomy.router)
api.include_router(notes.router)
api.include_router(cooklog.router)
api.include_router(favorite.router)
api.include_router(photos.router)
api.include_router(export.router)
api.include_router(importer.router)
api.include_router(shopping.router)
api.include_router(pantry.router)
api.include_router(share.router)
api.include_router(share.public_router)
api.include_router(todo.router)
app.include_router(api)
app.include_router(media.router)
