from __future__ import annotations

import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import urlparse


_PUBLIC_NAME = re.compile(r"^[A-Za-z0-9_]{5,32}$")


@dataclass(frozen=True)
class BotConfig:
    token: str
    parse_mode: str | None
    admin_ids: tuple[int, ...]


@dataclass(frozen=True)
class GroupConfig:
    enabled: bool
    chat_id: int | str | None
    join_url: str | None


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
class Config:
    bot: BotConfig
    group: GroupConfig
    runtime: RuntimeConfig
    network: NetworkConfig


def _section(data: dict[str, Any], name: str) -> dict[str, Any]:
    value = data.get(name)
    if not isinstance(value, dict):
        raise ValueError(f"Thiếu hoặc sai section '{name}' trong config.json")
    return value


def _text(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"'{key}' phải là chuỗi không rỗng trong config.json")
    return value.strip()


def _number(data: dict[str, Any], key: str, minimum: float = 0) -> float:
    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"'{key}' phải là số trong config.json")
    value = float(value)
    if value < minimum:
        raise ValueError(f"'{key}' phải >= {minimum:g} trong config.json")
    return value


def _admin_ids(data: dict[str, Any]) -> tuple[int, ...]:
    value = data.get("admin_ids", [])
    if not isinstance(value, list):
        raise ValueError("'bot.admin_ids' phải là mảng")

    if any(isinstance(item, bool) or not isinstance(item, int) for item in value):
        raise ValueError("Mỗi phần tử trong 'bot.admin_ids' phải là Telegram user ID")

    return tuple(dict.fromkeys(value))


def _public_chat_from_url(value: str) -> str | None:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    if parsed.netloc.lower() not in {"t.me", "www.t.me", "telegram.me", "www.telegram.me"}:
        return None

    path = parsed.path.strip("/")
    if not path or "/" in path or path.startswith("+") or path.startswith("joinchat"):
        return None
    if not _PUBLIC_NAME.fullmatch(path):
        return None
    return f"@{path}"


def _join_url(value: Any) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("'group.join_url' phải là URL hoặc null")

    url = value.strip()
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("'group.join_url' không phải URL hợp lệ")
    return url


def _group(data: dict[str, Any]) -> GroupConfig:
    value = data.get("group")
    if value is None:
        return GroupConfig(enabled=False, chat_id=None, join_url=None)
    if not isinstance(value, dict):
        raise ValueError("'group' phải là object trong config.json")

    enabled = value.get("enabled", False)
    if not isinstance(enabled, bool):
        raise ValueError("'group.enabled' phải là true hoặc false")
    if not enabled:
        return GroupConfig(enabled=False, chat_id=None, join_url=_join_url(value.get("join_url")))

    required = value.get("required_chat")
    if isinstance(required, bool) or not isinstance(required, (int, str)):
        raise ValueError("'group.required_chat' phải là chat ID, @username hoặc URL nhóm public")

    join_url = _join_url(value.get("join_url"))
    chat_id: int | str

    if isinstance(required, int):
        chat_id = required
    else:
        required = required.strip()
        if not required:
            raise ValueError("'group.required_chat' không được để trống")

        if required.lstrip("-").isdigit():
            chat_id = int(required)
        elif required.startswith("@"):
            username = required[1:]
            if not _PUBLIC_NAME.fullmatch(username):
                raise ValueError("'group.required_chat' có username Telegram không hợp lệ")
            chat_id = f"@{username}"
        elif required.startswith(("http://", "https://")):
            public_chat = _public_chat_from_url(required)
            if public_chat is None:
                raise ValueError(
                    "Link mời nhóm private không dùng làm required_chat. "
                    "Hãy dùng chat ID dạng -100... và để link mời ở group.join_url"
                )
            chat_id = public_chat
            if join_url is None:
                join_url = required
        elif _PUBLIC_NAME.fullmatch(required):
            chat_id = f"@{required}"
        else:
            raise ValueError("'group.required_chat' không hợp lệ")

    if join_url is None and isinstance(chat_id, str) and chat_id.startswith("@"):
        join_url = f"https://t.me/{chat_id[1:]}"

    if join_url is None:
        raise ValueError(
            "Nhóm dùng chat ID cần có 'group.join_url' để người dùng có nút tham gia"
        )

    return GroupConfig(enabled=True, chat_id=chat_id, join_url=join_url)


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
        bot=BotConfig(
            token=token,
            parse_mode=parse_mode,
            admin_ids=_admin_ids(bot),
        ),
        group=_group(data),
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
    )
