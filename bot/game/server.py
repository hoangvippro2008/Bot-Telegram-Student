from __future__ import annotations

from dataclasses import dataclass


SERVER_LIST = (
    "Vũ trụ 1:dragon1.teamobi.com:14445:0:0:0,"
    "Vũ trụ 2:dragon2.teamobi.com:14445:0:0:0,"
    "Vũ trụ 3:dragon3.teamobi.com:14445:0:0:0,"
    "Vũ trụ 4:dragon4.teamobi.com:14445:0:0:0,"
    "Vũ trụ 5:dragon5.teamobi.com:14445:0:0:0,"
    "Vũ trụ 6:dragon6.teamobi.com:14445:0:0:0,"
    "Vũ trụ 7:dragon7.teamobi.com:14445:0:0:0,"
    "Vũ trụ 8:dragon10.teamobi.com:14446:0:0:0,"
    "Vũ trụ 9:dragon10.teamobi.com:14447:0:0:0,"
    "Vũ trụ 10:dragon10.teamobi.com:14445:0:0:0,"
    "Vũ trụ 11:dragon11.teamobi.com:14445:0:0:0,"
    "Vũ trụ 12:dragon12.teamobi.com:14445:0:0:0,"
    "Võ đài liên vũ trụ:dragonwar.teamobi.com:20000:0:0:0,"
    "Universe 1:dragon.indonaga.com:14445:1:0:0,"
    "Naga:dragon.indonaga.com:14446:2:0:0,"
    "Super 1:dragon11.teamobi.com:14446:0:1:0,"
    "Super 2:dragonsuper.teamobi.com:17001:0:1:0,"
    "Vũ trụ 13:dragon13.teamobi.com:14446:0:0:0,"
    "VIP 2:dragon11.teamobi.com:18001:0:0:0,"
    "Vũ trụ 14:dragon14.teamobi.com:18001:0:0:0,"
    "Vũ trụ 15:dragon15.teamobi.com:14445:0:0:1,"
    "Super 3:dragonsuper3.teamobi.com:17001:0:1:1,"
    "0,0"
)


@dataclass(frozen=True)
class GameServer:
    id: int
    name: str
    host: str
    port: int
    language: int
    server_type: int
    is_new: bool


def parse_server_list(text: str) -> tuple[GameServer, ...]:
    value = text.replace("\x00", "").strip()
    if not value:
        raise ValueError("Danh sách máy chủ rỗng")

    parts = [part.strip() for part in value.split(",")]
    while parts and not parts[-1]:
        parts.pop()

    if len(parts) < 3:
        raise ValueError("Danh sách máy chủ không đúng định dạng")

    entries = parts
    if (
        len(parts) >= 2
        and parts[-1].lstrip("-").isdigit()
        and parts[-2].lstrip("-").isdigit()
    ):
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
        raise ValueError("Không tìm thấy máy chủ hợp lệ")

    return tuple(servers)


async def list_servers(timeout: float = 6.0) -> tuple[GameServer, ...]:
    del timeout
    return parse_server_list(SERVER_LIST)
