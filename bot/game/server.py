from __future__ import annotations

import asyncio
from dataclasses import dataclass, replace
from urllib.request import Request, urlopen


EXTRA_URL = "http://112.213.94.23/mod/server_extra.php"


@dataclass(frozen=True)
class GameServer:
    id: int
    name: str
    host: str
    port: int
    extra: bool = False


SERVERS = (
    GameServer(1, "Vũ trụ 1", "dragon1.teamobi.com", 14445),
    GameServer(2, "Vũ trụ 2", "dragon2.teamobi.com", 14445),
    GameServer(3, "Vũ trụ 3", "dragon3.teamobi.com", 14445),
    GameServer(4, "Vũ trụ 4", "dragon4.teamobi.com", 14445),
    GameServer(5, "Vũ trụ 5", "dragon5.teamobi.com", 14445),
    GameServer(6, "Vũ trụ 6", "dragon6.teamobi.com", 14445),
    GameServer(7, "Vũ trụ 7", "dragon7.teamobi.com", 14445),
    GameServer(8, "Vũ trụ 8", "dragon10.teamobi.com", 14446),
    GameServer(9, "Vũ trụ 9", "dragon10.teamobi.com", 14447),
    GameServer(10, "Vũ trụ 10", "dragon10.teamobi.com", 14445),
    GameServer(11, "Vũ trụ 11", "dragon11.teamobi.com", 14445),
    GameServer(12, "Võ đài liên vũ trụ", "dragonwar.teamobi.com", 20000),
)


def get_server(server_id: int) -> GameServer | None:
    return next((server for server in SERVERS if server.id == server_id), None)


def _resolve_extra(timeout: float) -> tuple[str, int] | None:
    request = Request(EXTRA_URL, headers={"User-Agent": "NRO-PC/2.5.0"})
    with urlopen(request, timeout=timeout) as response:
        text = response.read(128).decode("utf-8", errors="replace").strip()

    if ":" not in text:
        return None

    host, raw_port = text.split(":", 1)
    host = host.strip()
    raw_port = raw_port.strip()
    if not host or not raw_port.isdigit():
        return None

    port = int(raw_port)
    if not 1 <= port <= 65535:
        return None
    return host, port


async def list_servers(timeout: float = 4.0) -> tuple[GameServer, ...]:
    servers = list(SERVERS)
    try:
        extra = await asyncio.to_thread(_resolve_extra, timeout)
    except Exception:
        extra = None

    if extra is None:
        return tuple(servers)

    host, port = extra
    for index, server in enumerate(servers):
        if server.host == host and server.port == port:
            servers[index] = replace(server, extra=True)
            return tuple(servers)

    servers.insert(0, GameServer(0, "Máy chủ Extra", host, port, extra=True))
    return tuple(servers)
