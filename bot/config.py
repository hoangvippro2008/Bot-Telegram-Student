from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class BotConfig:
    token: str
    parse_mode: str | None


@dataclass(frozen=True)
class RuntimeConfig:
    drop_pending_updates: bool
    allowed_updates: tuple[str, ...]
    log_level: str
    bootstrap_retries: int


@dataclass(frozen=True)
class NetworkConfig:
    connect_timeout: float
    read_timeout: float
    error_log_interval: float


@dataclass(frozen=True)
class MessageConfig:
    start: str
    help: str
    unknown_command: str
    text_fallback: str


@dataclass(frozen=True)
class Config:
    bot: BotConfig
    runtime: RuntimeConfig
    network: NetworkConfig
    messages: MessageConfig


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"Thiếu hoặc sai section '{name}' trong config.json")
    return value


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' phải là chuỗi không rỗng trong config.json")
    return value


def _number(data: dict[str, Any], key: str, minimum: float = 0) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{key}' phải là số trong config.json")
    value = float(value)
    if value < minimum:
        raise ValueError(f"'{key}' phải >= {minimum:g} trong config.json")
    return value


def load_config(path: Path) -> Config:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise RuntimeError(f"Không tìm thấy config: {path}") from exc
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"config.json không hợp lệ tại dòng {exc.lineno}, cột {exc.colno}"
        ) from exc

    if not isinstance(data, dict):
        raise ValueError("config.json phải có object JSON ở cấp gốc")

    bot = _section(data, "bot")
    runtime = _section(data, "runtime")
    network = _section(data, "network")
    messages = _section(data, "messages")

    token = _text(bot, "token")
    if token == "PUT_BOT_TOKEN_HERE":
        raise ValueError("Chưa cấu hình bot.token trong config.json")

    parse_mode = bot.get("parse_mode")
    if parse_mode is not None:
        if not isinstance(parse_mode, str):
            raise ValueError("'bot.parse_mode' phải là chuỗi hoặc null")
        parse_mode = parse_mode.strip().upper()
        if parse_mode not in {"HTML", "MARKDOWN", "MARKDOWNV2"}:
            raise ValueError(
                "'bot.parse_mode' chỉ hỗ trợ HTML, MARKDOWN, MARKDOWNV2 hoặc null"
            )

    drop_pending = runtime.get("drop_pending_updates")
    if not isinstance(drop_pending, bool):
        raise ValueError("'runtime.drop_pending_updates' phải là true hoặc false")

    allowed = runtime.get("allowed_updates")
    if not isinstance(allowed, list) or not allowed:
        raise ValueError("'runtime.allowed_updates' phải là mảng không rỗng")
    if not all(isinstance(item, str) and item.strip() for item in allowed):
        raise ValueError("Mỗi phần tử trong 'runtime.allowed_updates' phải là chuỗi")

    log_level = _text(runtime, "log_level").upper()
    if log_level not in {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}:
        raise ValueError("'runtime.log_level' không hợp lệ")

    bootstrap_retries = runtime.get("bootstrap_retries")
    if isinstance(bootstrap_retries, bool) or not isinstance(bootstrap_retries, int):
        raise ValueError("'runtime.bootstrap_retries' phải là số nguyên")
    if bootstrap_retries < -1:
        raise ValueError("'runtime.bootstrap_retries' phải >= -1")

    return Config(
        bot=BotConfig(token=token, parse_mode=parse_mode),
        runtime=RuntimeConfig(
            drop_pending_updates=drop_pending,
            allowed_updates=tuple(item.strip() for item in allowed),
            log_level=log_level,
            bootstrap_retries=bootstrap_retries,
        ),
        network=NetworkConfig(
            connect_timeout=_number(network, "connect_timeout", 0.1),
            read_timeout=_number(network, "read_timeout", 0.1),
            error_log_interval=_number(network, "error_log_interval"),
        ),
        messages=MessageConfig(
            start=_text(messages, "start"),
            help=_text(messages, "help"),
            unknown_command=_text(messages, "unknown_command"),
            text_fallback=_text(messages, "text_fallback"),
        ),
    )
