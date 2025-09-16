from fastapi import FastAPI
# from app.logging_config import configure_logging
# from app.telemetry import setup_otel
from .routes import router

# configure_logging()
app = FastAPI(title="Tracklink Agent API", version="0.1.0")
# setup_otel(app)
app.include_router(router)
