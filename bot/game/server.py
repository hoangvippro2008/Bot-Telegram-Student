from __future__ import annotations

import asyncio
from dataclasses import dataclass
from urllib.request import Request, urlopen


EXTRA_URL = "http://112.213.94.23/mod/server_extra.php"
_MAX_RESPONSE = 256 * 1024


@dataclass(frozen=True)
class GameServer:
    id: int
    name: str
    host: str
    port: int
    language: int
    server_type: int
    is_new: bool


def _decode(raw: bytes) -> str:
    for encoding in ("utf-8-sig", "cp1258", "latin-1"):
        try:
            return raw.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError("Không đọc được nội dung server_extra.php")


def parse_server_list(text: str) -> tuple[GameServer, ...]:
    value = text.replace("\x00", "").strip()
    if not value:
        raise ValueError("server_extra.php trả dữ liệu rỗng")

    parts = [part.strip() for part in value.split(",")]
    while parts and not parts[-1]:
        parts.pop()

    if len(parts) < 3:
        raise ValueError("Danh sách máy chủ không đúng định dạng")

    entries = parts
    if len(parts) >= 2 and parts[-1].lstrip("-").isdigit() and parts[-2].lstrip("-").isdigit():
        entries = parts[:-2]

    servers: list[GameServer] = []
    for raw_entry in entries:
        if not raw_entry:
            continue

        fields = [field.strip() for field in raw_entry.split(":")]
        if len(fields) != 6:
            raise ValueError(f"Máy chủ sai định dạng: {raw_entry}")

        name, host, raw_port, raw_language, raw_type, raw_new = fields
        if not name or not host:
            raise ValueError(f"Máy chủ thiếu tên hoặc host: {raw_entry}")
        if not raw_port.isdigit():
            raise ValueError(f"Port máy chủ không hợp lệ: {raw_entry}")
        if not raw_language.lstrip("-").isdigit():
            raise ValueError(f"Language máy chủ không hợp lệ: {raw_entry}")
        if not raw_type.lstrip("-").isdigit():
            raise ValueError(f"Type máy chủ không hợp lệ: {raw_entry}")
        if not raw_new.lstrip("-").isdigit():
            raise ValueError(f"isNew máy chủ không hợp lệ: {raw_entry}")

        port = int(raw_port)
        if not 1 <= port <= 65535:
            raise ValueError(f"Port máy chủ ngoài phạm vi: {raw_entry}")

        servers.append(
            GameServer(
                id=len(servers) + 1,
                name=name,
                host=host,
                port=port,
                language=int(raw_language),
                server_type=int(raw_type),
                is_new=int(raw_new) != 0,
            )
        )

    if not servers:
        raise ValueError("Không tìm thấy máy chủ hợp lệ trong server_extra.php")

    return tuple(servers)


def _download_server_list(timeout: float) -> str:
    request = Request(
        EXTRA_URL,
        headers={
            "User-Agent": "NRO-PC/2.5.0",
            "Accept": "text/plain,*/*",
            "Cache-Control": "no-cache",
        },
    )
    with urlopen(request, timeout=timeout) as response:
        raw = response.read(_MAX_RESPONSE + 1)

    if len(raw) > _MAX_RESPONSE:
        raise ValueError("Danh sách máy chủ vượt giới hạn cho phép")

    return _decode(raw)


async def list_servers(timeout: float = 6.0) -> tuple[GameServer, ...]:
    try:
        text = await asyncio.to_thread(_download_server_list, timeout)
        return parse_server_list(text)
    except Exception as exc:
        raise RuntimeError(f"Không lấy được danh sách máy chủ: {exc}") from exc
