from __future__ import annotations

import asyncio
import os
import time
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


def _error_message(exc: Exception) -> str:
    message = str(exc).strip()
    return message or exc.__class__.__name__


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
        "last_scan_at": None,
        "next_scan_at": None,
        "scan_count": 0,
        "auto_loop_running": False,
        "task": None,
    }


async def scan_loop() -> None:
    settings: Settings = runtime["settings"]
    engine: CopyTradingEngine = runtime["engine"]
    runtime["auto_loop_running"] = True
    while True:
        runtime["next_scan_at"] = int(time.time())
        try:
            runtime["last_summary"] = await engine.run_once()
            runtime["last_scan_at"] = int(time.time())
            runtime["scan_count"] = int(runtime.get("scan_count") or 0) + 1
            runtime["last_error"] = None
        except Exception as exc:
            runtime["last_error"] = _error_message(exc)
            runtime["last_scan_at"] = int(time.time())
        runtime["next_scan_at"] = int(time.time()) + settings.poll_interval_seconds
        await asyncio.sleep(settings.poll_interval_seconds)


@app.on_event("startup")
async def startup() -> None:
    runtime.update(build_runtime())
    settings: Settings = runtime["settings"]
    if settings.auto_start:
        runtime["task"] = asyncio.create_task(scan_loop())
    else:
        runtime["auto_loop_running"] = False


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
        "automation": {
            "enabled": settings.auto_start,
            "running": bool(runtime.get("task") and not runtime["task"].done()),
            "poll_interval_seconds": settings.poll_interval_seconds,
            "last_scan_at": runtime.get("last_scan_at"),
            "next_scan_at": runtime.get("next_scan_at"),
            "scan_count": runtime.get("scan_count") or 0,
        },
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
    runtime["last_scan_at"] = int(time.time())
    runtime["scan_count"] = int(runtime.get("scan_count") or 0) + 1
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


@app.get("/leaderboard")
async def leaderboard(
    category: str = "SPORTS",
    time_period: str = "WEEK",
    order_by: str = "PNL",
    limit: int = 25,
    offset: int = 0,
) -> Dict[str, Any]:
    public: PolymarketPublicClient = runtime["public"]
    items = await public.fetch_leaderboard(
        category=category,
        time_period=time_period,
        order_by=order_by,
        limit=limit,
        offset=offset,
    )
    return {"wallets": items}


@app.get("/diagnostics")
async def diagnostics() -> Dict[str, Any]:
    settings: Settings = runtime["settings"]
    public: PolymarketPublicClient = runtime["public"]
    result: Dict[str, Any] = {
        "configured_wallets": len(settings.smart_wallets),
        "copy_amount_usdc": settings.copy_amount_usdc,
        "execution_mode": settings.execution_mode,
        "checks": {},
    }

    try:
        geoblock = await public.geoblock()
        result["checks"]["geoblock"] = {"ok": True, "payload": geoblock}
    except Exception as exc:
        result["checks"]["geoblock"] = {"ok": False, "error": _error_message(exc)}

    try:
        leaders = await public.fetch_leaderboard(category="SPORTS", time_period="WEEK", order_by="PNL", limit=3)
        result["checks"]["sports_leaderboard"] = {
            "ok": True,
            "count": len(leaders),
            "sample_wallets": [item.get("proxyWallet") for item in leaders if item.get("proxyWallet")],
        }
    except Exception as exc:
        result["checks"]["sports_leaderboard"] = {"ok": False, "error": _error_message(exc)}

    if settings.smart_wallets:
        wallet = settings.smart_wallets[0]
        try:
            trades = await public.fetch_wallet_trades(wallet, min(settings.activity_limit, 10))
            result["checks"]["first_wallet_activity"] = {
                "ok": True,
                "wallet": wallet,
                "raw_count": len(trades),
            }
        except Exception as exc:
            result["checks"]["first_wallet_activity"] = {
                "ok": False,
                "wallet": wallet,
                "error": _error_message(exc),
            }
    else:
        result["checks"]["first_wallet_activity"] = {
            "ok": False,
            "error": "未配置 SMART_WALLETS",
        }

    return result


if __name__ == "__main__":
    import uvicorn

    port = int(os.getenv("PORT", "8080"))
    uvicorn.run("app.main:app", host="0.0.0.0", port=port)
