from fastapi import FastAPI

from .routers import sources, vendors

app = FastAPI()
app.include_router(sources.router)
app.include_router(vendors.router)
