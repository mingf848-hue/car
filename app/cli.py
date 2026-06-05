from __future__ import annotations

import asyncio

from dotenv import load_dotenv

from .config import Settings
from .engine import CopyTradingEngine
from .executor import build_executor
from .market_filter import DeepSeekSportsClassifier
from .polymarket_client import PolymarketPublicClient
from .state import StateStore


async def main() -> None:
    load_dotenv()
    settings = Settings.from_env()
    state = StateStore(settings.sqlite_path)
    public = PolymarketPublicClient(settings)
    executor = build_executor(settings)
    engine = CopyTradingEngine(
        settings=settings,
        state=state,
        public_client=public,
        executor=executor,
        classifier=DeepSeekSportsClassifier(settings),
    )
    summary = await engine.run_once()
    print(summary)


if __name__ == "__main__":
    asyncio.run(main())
