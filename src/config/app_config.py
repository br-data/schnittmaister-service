import logging
from contextlib import asynccontextmanager
from typing import AsyncGenerator

from fastapi import FastAPI

# Where the service listens; only on this machine, since it reads local video files
HOST = "127.0.0.1"
PORT = 3000


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:
    """
    Manage the lifespan of the FastAPI application.

    :param app: The FastAPI application instance.
    """
    logging.info(f"Application startup successful. Open the API docs at http://{HOST}:{PORT}/docs")
    yield


APP = FastAPI(
    title="SchnittmAIster API",
    description=(
        "Turns a video into a cut proposal with Gemini and returns it as an XMEML file "
        "for Premiere Pro or Final Cut Pro 7."
    ),
    version="0.1",
    lifespan=lifespan,
)
