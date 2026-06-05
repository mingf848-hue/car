from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .config import Settings
from .engine import CopyTradingEngine
from .executor import build_executor
from .market_filter import DeepSeekSportsClassifier
from .polymarket_client import PolymarketPublicClient
from .scoring import score_wallets
from .state import StateStore

load_dotenv()

app = FastAPI(title="Polymarket Sports Copy Bot", version="0.1.0")
runtime: Dict[str, Any] = {}
static_dir = os.path.join(os.path.dirname(__file__), "static")
app.mount("/static", StaticFiles(directory=static_dir), name="static")


class ScoreWalletsRequest(BaseModel):
    wallets: Optional[List[str]] = None


def build_runtime() -> Dict[str, Any]:
    settings = Settings.from_env()
    state = StateStore(settings.sqlite_path)
    public = PolymarketPublicClient(settings)
    executor = build_executor(settings)
    classifier = DeepSeekSportsClassifier(settings)
    engine = CopyTradingEngine(settings, state, public, executor, classifier)
    return {
        "settings": settings,
        "state": state,
        "public": public,
        "executor": executor,
        "classifier": classifier,
        "engine": engine,
        "last_summary": None,
        "last_error": None,
        "task": None,
    }


async def scan_loop() -> None:
    settings: Settings = runtime["settings"]
    engine: CopyTradingEngine = runtime["engine"]
    while True:
        try:
            runtime["last_summary"] = await engine.run_once()
            runtime["last_error"] = None
        except Exception as exc:
            runtime["last_error"] = str(exc)
        await asyncio.sleep(settings.poll_interval_seconds)


@app.on_event("startup")
async def startup() -> None:
    runtime.update(build_runtime())
    settings: Settings = runtime["settings"]
    if settings.auto_start:
        runtime["task"] = asyncio.create_task(scan_loop())


@app.on_event("shutdown")
async def shutdown() -> None:
    task = runtime.get("task")
    if task:
        task.cancel()


@app.get("/")
async def root() -> FileResponse:
    return FileResponse(os.path.join(static_dir, "index.html"))


@app.get("/api/status")
async def api_status() -> Dict[str, Any]:
    settings: Settings = runtime["settings"]
    return {
        "name": "polymarket-sports-copy-bot",
        "config": settings.redacted(),
        "stats": runtime["state"].stats(),
        "last_summary": runtime.get("last_summary"),
        "last_error": runtime.get("last_error"),
    }


@app.get("/health")
async def health() -> Dict[str, Any]:
    settings: Settings = runtime["settings"]
    return {
        "ok": True,
        "mode": settings.execution_mode,
        "live_trading_enabled": settings.live_trading_enabled,
        "wallets": len(settings.smart_wallets),
        "copy_amount_usdc": settings.copy_amount_usdc,
    }


@app.post("/scan")
async def scan() -> Dict[str, Any]:
    engine: CopyTradingEngine = runtime["engine"]
    summary = await engine.run_once()
    runtime["last_summary"] = summary
    return summary


@app.get("/events")
async def events(limit: int = 50) -> Dict[str, Any]:
    state: StateStore = runtime["state"]
    return {"events": state.recent_events(limit)}


@app.get("/positions")
async def positions(include_closed: bool = False) -> Dict[str, Any]:
    state: StateStore = runtime["state"]
    return {"positions": state.positions(include_closed=include_closed)}


@app.post("/score-wallets")
async def score_wallets_endpoint(payload: ScoreWalletsRequest) -> Dict[str, Any]:
    settings: Settings = runtime["settings"]
    public: PolymarketPublicClient = runtime["public"]
    wallets = payload.wallets or list(settings.smart_wallets)
    return {"wallets": await score_wallets(settings, public, wallets)}


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
