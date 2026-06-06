from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple


def _csv(value: Optional[str]) -> Tuple[str, ...]:
    if not value:
        return ()
    return tuple(item.strip() for item in re.split(r"[\s,;]+", value) if item.strip())


def _bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "y", "on"}


def _float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return float(value)


def _int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None or value.strip() == "":
        return default
    return int(value)


def _sqlite_path() -> Path:
    explicit = os.getenv("SQLITE_PATH", "").strip()
    if explicit:
        return Path(explicit)
    if Path("/data").exists():
        return Path("/data/bot.sqlite3")
    return Path("data/bot.sqlite3")


@dataclass(frozen=True)
class Settings:
    data_api_host: str = "https://data-api.polymarket.com"
    gamma_api_host: str = "https://gamma-api.polymarket.com"
    clob_host: str = "https://clob.polymarket.com"
    geoblock_url: str = "https://polymarket.com/api/geoblock"
    chain_id: int = 137

    smart_wallets: Tuple[str, ...] = ()
    copy_amount_usdc: float = 5.0
    execution_mode: str = "dry_run"
    ack_trading_risks: bool = False
    auto_start: bool = True
    copy_historical_on_first_run: bool = False
    poll_interval_seconds: int = 5
    activity_limit: int = 60

    sports_only: bool = True
    use_deepseek_classifier: bool = True
    deepseek_api_key: str = ""
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-chat"

    min_leader_usdc_size: float = 1.0
    max_live_daily_usdc: float = 50.0
    max_slippage_bps: int = 150
    require_price_check: bool = True
    cooldown_seconds_per_token: int = 120
    auto_follow_sells: bool = True
    sell_mode: str = "close_full_on_leader_sell"
    min_sell_shares: float = 0.01

    block_on_geoblock: bool = True
    close_only_country_codes: Tuple[str, ...] = ("SG",)

    polymarket_private_key: str = ""
    polymarket_funder: str = ""
    polymarket_signature_type: Optional[int] = None
    clob_api_key: str = ""
    clob_api_secret: str = ""
    clob_api_passphrase: str = ""
    derive_api_key_if_missing: bool = True

    sqlite_path: Path = Path("data/bot.sqlite3")

    @classmethod
    def from_env(cls) -> "Settings":
        sig_type_raw = os.getenv("POLYMARKET_SIGNATURE_TYPE", "").strip()
        signature_type = int(sig_type_raw) if sig_type_raw else None
        amount = _float("COPY_AMOUNT_USDC", 5.0)
        if amount <= 0:
            raise ValueError("COPY_AMOUNT_USDC must be greater than 0")

        return cls(
            data_api_host=os.getenv("POLYMARKET_DATA_API_HOST", cls.data_api_host),
            gamma_api_host=os.getenv("POLYMARKET_GAMMA_API_HOST", cls.gamma_api_host),
            clob_host=os.getenv("POLYMARKET_CLOB_HOST", cls.clob_host),
            geoblock_url=os.getenv("POLYMARKET_GEOBLOCK_URL", cls.geoblock_url),
            chain_id=_int("POLYMARKET_CHAIN_ID", cls.chain_id),
            smart_wallets=_csv(os.getenv("SMART_WALLETS")),
            copy_amount_usdc=amount,
            execution_mode=os.getenv("EXECUTION_MODE", "dry_run").strip().lower(),
            ack_trading_risks=_bool("ACK_TRADING_RISKS", False),
            auto_start=_bool("AUTO_START", True),
            copy_historical_on_first_run=_bool("COPY_HISTORICAL_ON_FIRST_RUN", False),
            poll_interval_seconds=_int("POLL_INTERVAL_SECONDS", 5),
            activity_limit=_int("ACTIVITY_LIMIT", 60),
            sports_only=_bool("SPORTS_ONLY", True),
            use_deepseek_classifier=_bool("USE_DEEPSEEK_CLASSIFIER", True),
            deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip(),
            deepseek_base_url=os.getenv("DEEPSEEK_BASE_URL", cls.deepseek_base_url),
            deepseek_model=os.getenv("DEEPSEEK_MODEL", cls.deepseek_model),
            min_leader_usdc_size=_float("MIN_LEADER_USDC_SIZE", 1.0),
            max_live_daily_usdc=_float("MAX_LIVE_DAILY_USDC", 50.0),
            max_slippage_bps=_int("MAX_SLIPPAGE_BPS", 150),
            require_price_check=_bool("REQUIRE_PRICE_CHECK", True),
            cooldown_seconds_per_token=_int("COOLDOWN_SECONDS_PER_TOKEN", 120),
            auto_follow_sells=_bool("AUTO_FOLLOW_SELLS", True),
            sell_mode=os.getenv("SELL_MODE", cls.sell_mode).strip().lower(),
            min_sell_shares=_float("MIN_SELL_SHARES", 0.01),
            block_on_geoblock=_bool("BLOCK_ON_GEOBLOCK", True),
            close_only_country_codes=_csv(os.getenv("CLOSE_ONLY_COUNTRY_CODES")) or ("SG",),
            polymarket_private_key=os.getenv("POLYMARKET_PRIVATE_KEY", "").strip(),
            polymarket_funder=os.getenv("POLYMARKET_FUNDER", "").strip(),
            polymarket_signature_type=signature_type,
            clob_api_key=os.getenv("CLOB_API_KEY", "").strip(),
            clob_api_secret=os.getenv("CLOB_API_SECRET", "").strip(),
            clob_api_passphrase=os.getenv("CLOB_API_PASSPHRASE", "").strip(),
            derive_api_key_if_missing=_bool("DERIVE_API_KEY_IF_MISSING", True),
            sqlite_path=_sqlite_path(),
        )

    @property
    def live_trading_enabled(self) -> bool:
        return self.execution_mode == "live" and self.ack_trading_risks

    def redacted(self) -> dict:
        return {
            "execution_mode": self.execution_mode,
            "live_trading_enabled": self.live_trading_enabled,
            "copy_amount_usdc": self.copy_amount_usdc,
            "auto_start": self.auto_start,
            "sports_only": self.sports_only,
            "deepseek_classifier": bool(self.use_deepseek_classifier and self.deepseek_api_key),
            "poll_interval_seconds": self.poll_interval_seconds,
            "max_slippage_bps": self.max_slippage_bps,
            "max_live_daily_usdc": self.max_live_daily_usdc,
            "auto_follow_sells": self.auto_follow_sells,
            "sell_mode": self.sell_mode,
            "sqlite_path": str(self.sqlite_path),
            "storage": {
                "sqlite_path": str(self.sqlite_path),
                "volume_path": "/data",
                "using_volume_path": str(self.sqlite_path).startswith("/data/"),
            },
            "execution_wallet": {
                "private_key_configured": bool(self.polymarket_private_key),
                "funder_configured": bool(self.polymarket_funder),
                "signature_type_configured": self.polymarket_signature_type is not None,
                "clob_credentials_configured": bool(
                    self.clob_api_key and self.clob_api_secret and self.clob_api_passphrase
                ),
                "derive_api_key_if_missing": self.derive_api_key_if_missing,
            },
        }
