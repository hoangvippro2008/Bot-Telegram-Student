from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from time import monotonic

from bot.game.protocol import BufferReader, BufferWriter, GameProtocol, Packet
from bot.game.server import GameServer


logger = logging.getLogger(__name__)

_VERSION = "2.5.0"
_PLATFORM = "Pc platform xxx"
_CLIENT_TYPE = 4
_ZOOM_LEVEL = 1
_SERVER15_HOST = "dragon15.teamobi.com"
_SERVER15_INFO = bytes.fromhex(
    "526172211a0700cf907300000d00000000000000baa47424943700300000002000000002"
    "9ce4200fea592b571d330a0020000000696e666f5f342e747874a5ea17f7234e09cd00f0"
    "4f4b455b7fb7c8c21534e06e28e14e5bffb08d5bd1fbe5defec9d3f6d327afe67cc2d4"
    "d5a7276db80a60c91dfdf541b18038bbc43d7b00400700"
)


@dataclass
class TaskState:
    task_id: int
    index: int
    name: str
    detail: str
    sub_names: list[str] = field(default_factory=list)
    sub_details: list[str] = field(default_factory=list)
    counts: list[int] = field(default_factory=list)
    count: int = 0

    @property
    def current_name(self) -> str | None:
        if 0 <= self.index < len(self.sub_names):
            return self.sub_names[self.index]
        return None

    @property
    def current_detail(self) -> str | None:
        if 0 <= self.index < len(self.sub_details):
            return self.sub_details[self.index] or None
        return None

    @property
    def target(self) -> int | None:
        if 0 <= self.index < len(self.counts):
            return self.counts[self.index]
        return None


@dataclass
class CharacterState:
    player_id: int | None = None
    task_id: int | None = None
    name: str | None = None
    power: int | None = None
    gold: int | None = None
    gem: int | None = None
    locked_gem: int | None = None
    task: TaskState | None = None
    mission_notice: str | None = None


class GameClient:
    def __init__(
        self,
        server: GameServer,
        account: str,
        password: str,
        connect_timeout: float = 8.0,
    ):
        self.server = server
        self.account = account
        self._password = password
        self.connect_timeout = connect_timeout
        self.protocol = GameProtocol()
        self.reader: asyncio.StreamReader | None = None
        self.writer: asyncio.StreamWriter | None = None
        self.reader_task: asyncio.Task | None = None
        self._finish_map_task: asyncio.Task | None = None
        self.character = CharacterState()
        self.status = "Chưa kết nối"
        self.error: str | None = None
        self.connected_at: float | None = None
        self._handshake = asyncio.Event()
        self._character_ready = asyncio.Event()
        self._task_ready = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._received_commands: list[int] = []
        self._sync_pending: set[str] = set()
        self._sync_started = False
        self._sync_finished = False
        self._server_versions: tuple[int, int, int, int] | None = None

    @property
    def connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing() and self.error is None

    @property
    def _is_server15(self) -> bool:
        return self.server.host.casefold() == _SERVER15_HOST

    @property
    def uptime(self) -> float:
        if self.connected_at is None:
            return 0.0
        return max(0.0, monotonic() - self.connected_at)

    async def connect(self) -> None:
        await self.disconnect()
        self.protocol = GameProtocol()
        self.character = CharacterState()
        self.error = None
        self._handshake = asyncio.Event()
        self._character_ready = asyncio.Event()
        self._task_ready = asyncio.Event()
        self._received_commands.clear()
        self._sync_pending.clear()
        self._sync_started = False
        self._sync_finished = False
        self._server_versions = None
        self.status = "Đang kết nối"

        try:
            logger.info(
                "Game connect: %s -> %s:%s",
                self.server.name,
                self.server.host,
                self.server.port,
            )
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.server.host, self.server.port),
                timeout=self.connect_timeout,
            )
            self.connected_at = monotonic()
            self.reader_task = asyncio.create_task(self._read_loop())

            await self._send(-27, b"")
            await self._wait(self._handshake, 6.0, "Không nhận được key từ máy chủ")

            self.status = "Đang đăng nhập"
            if self._is_server15:
                await self._login_server15()
            else:
                await self._send_client_info()
                await asyncio.sleep(0.5)
                await self._send_image_source()
                await asyncio.sleep(0.3)
                await self._send_login()

            await self._wait(
                self._character_ready,
                30.0,
                "Không nhận được dữ liệu nhân vật (-30/0) sau đăng nhập",
            )

            try:
                await asyncio.wait_for(self._task_ready.wait(), timeout=2.5)
            except TimeoutError:
                pass

            self.status = "Đã kết nối"
        except Exception as exc:
            self.error = str(exc)
            self.status = "Lỗi kết nối"
            await self.disconnect(keep_error=True)
            raise

    async def disconnect(self, keep_error: bool = False) -> None:
        finish_map_task = self._finish_map_task
        self._finish_map_task = None
        if finish_map_task and finish_map_task is not asyncio.current_task():
            finish_map_task.cancel()
            try:
                await finish_map_task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        task = self.reader_task
        self.reader_task = None
        if task and task is not asyncio.current_task():
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
            except Exception:
                pass

        writer = self.writer
        self.writer = None
        self.reader = None
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

        self.connected_at = None
        if not keep_error:
            self.error = None
            self.status = "Chưa kết nối"

    async def _wait(self, event: asyncio.Event, timeout: float, message: str) -> None:
        try:
            await asyncio.wait_for(event.wait(), timeout=timeout)
        except TimeoutError as exc:
            if self.error:
                raise RuntimeError(self.error) from exc
            commands = ", ".join(str(command) for command in self._received_commands[-12:])
            if commands:
                message = f"{message}. Cmd đã nhận: {commands}"
            raise RuntimeError(message) from exc
        if self.error:
            raise RuntimeError(self.error)

    async def _send(self, command: int, payload: bytes = b"") -> None:
        writer = self.writer
        if writer is None or writer.is_closing():
            raise RuntimeError("Socket chưa kết nối")

        raw = self.protocol.encode_packet(command, payload)
        async with self._write_lock:
            writer.write(raw)
            await writer.drain()

    async def _send_client_info(self) -> None:
        if self._is_server15:
            payload = (
                BufferWriter()
                .u8(2)
                .u8(_CLIENT_TYPE)
                .u8(4)
                .boolean(False)
                .i32(960)
                .i32(540)
                .boolean(True)
                .boolean(True)
                .utf(f"{_PLATFORM}|{_VERSION}")
                .i16(len(_SERVER15_INFO))
                .build()
                + _SERVER15_INFO
            )
            await self._send(-29, payload)
            logger.info(
                "Game server 15: đã gửi ClientType tương thích + info (%s bytes)",
                len(_SERVER15_INFO),
            )
            return

        payload = (
            BufferWriter()
            .u8(2)
            .u8(_CLIENT_TYPE)
            .u8(_ZOOM_LEVEL)
            .boolean(False)
            .i32(800)
            .i32(600)
            .boolean(True)
            .boolean(False)
            .utf(f"{_PLATFORM}|{_VERSION}")
            .build()
        )
        await self._send(-29, payload)

    async def _login_server15(self) -> None:
        logger.info("Game server 15: dùng luồng bootstrap tương thích 2.5.0")
        await self._send_client_info()
        await asyncio.sleep(2.0)
        await self._send_image_source()
        await asyncio.sleep(1.0)
        await self._send_login()
        await asyncio.sleep(1.0)

        self.status = "Đang tải dữ liệu game"
        await self._send(-28, BufferWriter().u8(6).build())
        await self._send(-28, BufferWriter().u8(7).build())
        await self._send(-28, BufferWriter().u8(8).build())
        await self._send(-87, b"")
        logger.info("Game server 15: đã request Map/Skill/Item/Data")

        await asyncio.sleep(1.0)
        self.status = "Đang hoàn tất đồng bộ"
        self._sync_finished = True
        await self._send(-28, BufferWriter().u8(13).build())
        await self._send(-38, b"")
        logger.info("Game server 15: clientOk + finishUpdate đã gửi")

        if self._finish_map_task is None or self._finish_map_task.done():
            self._finish_map_task = asyncio.create_task(self._finish_load_map())

    async def _send_image_source(self) -> None:
        payload = BufferWriter().i16(0).build()
        await self._send(-111, payload)
        logger.debug("Game login: đã gửi ImageSource rỗng")

    async def _send_login(self) -> None:
        payload = (
            BufferWriter()
            .u8(0)
            .utf(self.account)
            .utf(self._password)
            .utf(_VERSION)
            .u8(0)
            .build()
        )
        await self._send(-29, payload)

    async def _read_loop(self) -> None:
        reader = self.reader
        if reader is None:
            return

        try:
            while True:
                packet = await self.protocol.read_packet(reader)
                self._received_commands.append(packet.command)
                if len(self._received_commands) > 32:
                    del self._received_commands[:-32]
                logger.debug(
                    "Game packet nhận cmd=%s size=%s",
                    packet.command,
                    len(packet.data),
                )
                await self._handle(packet)
        except asyncio.CancelledError:
            raise
        except asyncio.IncompleteReadError:
            if self.status not in {"Chưa kết nối", "Lỗi kết nối"}:
                self.error = "Máy chủ đã đóng kết nối"
        except Exception as exc:
            logger.debug("Lỗi socket game: %s", exc, exc_info=True)
            self.error = str(exc)
        finally:
            if self.error:
                self.status = "Mất kết nối"
            self._handshake.set()
            self._character_ready.set()
            self._task_ready.set()

    async def _handle(self, packet: Packet) -> None:
        if packet.command == -27:
            self._handle_key(packet.data)
            return
        if packet.command == 2:
            self.error = (
                f"Máy chủ {self.server.name} báo tài khoản chưa có nhân vật "
                "(cmd 2 / CREATE_CHAR)"
            )
            self._character_ready.set()
            return
        if packet.command == -87:
            await self._complete_sync_part("data", len(packet.data))
            return
        if packet.command == 12:
            await self._complete_sync_part("item", len(packet.data))
            return
        if packet.command == -28:
            await self._handle_not_map(packet.data)
            return
        if packet.command == -30:
            self._handle_subcommand(packet.data)
            return
        if packet.command == 92:
            self._handle_game_message(packet.data)
            return
        if packet.command == 40:
            self._handle_task(packet.data)
            return
        if packet.command == 41:
            if self.character.task:
                self.character.task.index += 1
                self.character.task.count = 0
                self._task_ready.set()
            return
        if packet.command == 43:
            self._handle_task_update(packet.data)
            return
        if packet.command == 6:
            self._handle_money_update(packet.data)

    async def _handle_not_map(self, data: bytes) -> None:
        reader = BufferReader(data)
        if not reader.remaining:
            return

        subcommand = reader.u8()
        logger.debug(
            "Game packet -28 sub=%s size=%s",
            subcommand,
            len(data),
        )

        if subcommand == 4:
            if self._is_server15:
                if reader.remaining >= 5:
                    vs_data = reader.u8()
                    vs_map = reader.u8()
                    vs_skill = reader.u8()
                    vs_item = reader.u8()
                    extra = reader.u8()
                    self._server_versions = (vs_data, vs_map, vs_skill, vs_item)
                    logger.info(
                        "Game server 15: versions data=%s map=%s skill=%s item=%s extra=%s",
                        vs_data,
                        vs_map,
                        vs_skill,
                        vs_item,
                        extra,
                    )
                return

            await self._start_sync(reader)
            return

        if subcommand == 6:
            await self._complete_sync_part("map", reader.remaining)
            return

        if subcommand == 7:
            await self._complete_sync_part("skill", reader.remaining)
            return

        if subcommand == 8:
            if reader.remaining < 2:
                logger.warning("Game sync: packet item thiếu version/part")
                return
            version = reader.u8()
            part = reader.u8()
            logger.info(
                "Game sync: nhận Item version=%s part=%s size=%s",
                version,
                part,
                reader.remaining,
            )
            return

    async def _start_sync(self, reader: BufferReader) -> None:
        if self._sync_started:
            return
        if reader.remaining < 5:
            raise ValueError("Packet -28/4 thiếu version Data/Map/Skill/Item")

        vs_data = reader.u8()
        vs_map = reader.u8()
        vs_skill = reader.u8()
        vs_item = reader.u8()
        extra = reader.u8()
        self._server_versions = (vs_data, vs_map, vs_skill, vs_item)
        self._sync_started = True
        self._sync_pending = {"data", "map", "skill", "item"}
        self.status = "Đang tải dữ liệu game"

        logger.info(
            "Game sync: server versions data=%s map=%s skill=%s item=%s extra=%s",
            vs_data,
            vs_map,
            vs_skill,
            vs_item,
            extra,
        )

        await self._send(-87, b"")
        await self._send(-28, BufferWriter().u8(6).build())
        await self._send(-28, BufferWriter().u8(7).build())
        await self._send(-28, BufferWriter().u8(8).build())
        logger.info("Game sync: đã request Data/Map/Skill/Item")

    async def _complete_sync_part(self, part: str, size: int) -> None:
        if not self._sync_started or part not in self._sync_pending:
            return

        self._sync_pending.remove(part)
        logger.info(
            "Game sync: xong %s (%s bytes), còn %s",
            part,
            size,
            ", ".join(sorted(self._sync_pending)) or "0",
        )

        if self._sync_pending or self._sync_finished:
            return

        self._sync_finished = True
        self.status = "Đang hoàn tất đồng bộ"
        await self._send(-28, BufferWriter().u8(13).build())
        await self._send(-38, b"")
        logger.info("Game sync: clientOk + finishUpdate đã gửi")

        if self._finish_map_task is None or self._finish_map_task.done():
            self._finish_map_task = asyncio.create_task(self._finish_load_map())

    async def _finish_load_map(self) -> None:
        await asyncio.sleep(4.0)
        if self.writer is None or self.writer.is_closing():
            return
        await self._send(-39, b"")
        logger.info("Game login: finishLoadMap (-39) đã gửi")

    def _handle_key(self, data: bytes) -> None:
        reader = BufferReader(data)
        size = reader.u8()
        self.protocol.set_key(reader.bytes(size))
        if reader.remaining >= 2:
            try:
                secondary_host = reader.utf()
                secondary_port = reader.i32() if reader.remaining >= 4 else 0
                secondary_enabled = reader.u8() != 0 if reader.remaining else False
                logger.info(
                    "Game handshake: main=%s:%s | secondary=%s:%s | enabled=%s",
                    self.server.host,
                    self.server.port,
                    secondary_host or "-",
                    secondary_port,
                    secondary_enabled,
                )
            except ValueError:
                pass
        self._handshake.set()

    def _handle_subcommand(self, data: bytes) -> None:
        reader = BufferReader(data)
        if not reader.remaining:
            return
        subcommand = reader.u8()

        if subcommand == 4:
            if reader.remaining < 32:
                return
            self.character.gold = reader.i64()
            self.character.gem = reader.i32()
            reader.i64()
            reader.i64()
            self.character.locked_gem = reader.i32()
            logger.info(
                "Game login: cập nhật tiền vàng=%s ngọc=%s ngọc_khóa=%s",
                self.character.gold,
                self.character.gem,
                self.character.locked_gem,
            )
            return

        if subcommand != 0:
            return

        self.character.player_id = reader.i32()
        self.character.task_id = reader.u8()
        reader.u8()
        reader.i16()
        self.character.name = reader.utf()
        reader.u8()
        reader.u8()
        self.character.power = reader.i64()
        reader.i16()
        reader.i16()
        reader.u8()

        skill_count = reader.u8()
        for _ in range(skill_count):
            reader.i16()

        self.character.gold = reader.i64()
        self.character.locked_gem = reader.i32()
        self.character.gem = reader.i32()
        logger.info(
            "Game login: nhận nhân vật %s (id=%s), vàng=%s ngọc=%s ngọc_khóa=%s",
            self.character.name,
            self.character.player_id,
            self.character.gold,
            self.character.gem,
            self.character.locked_gem,
        )
        self._character_ready.set()

    def _handle_game_message(self, data: bytes) -> None:
        reader = BufferReader(data)
        try:
            name = reader.utf()
            message = reader.utf()
        except ValueError:
            return

        if name:
            return

        self.character.mission_notice = message
        if message.startswith(
            ("Nhiệm vụ của bạn là", "Your mission is", "Misimu adalah")
        ):
            logger.info("Game login: nhận thông báo nhiệm vụ")
            self._task_ready.set()

    def _handle_money_update(self, data: bytes) -> None:
        reader = BufferReader(data)
        if reader.remaining < 16:
            return
        self.character.gold = reader.i64()
        self.character.gem = reader.i32()
        self.character.locked_gem = reader.i32()

    def _handle_task(self, data: bytes) -> None:
        reader = BufferReader(data)
        task_id = reader.i16()
        index = reader.u8()
        name = reader.utf()
        detail = reader.utf()
        size = reader.u8()
        sub_names: list[str] = []
        sub_details: list[str] = []

        for _ in range(size):
            sub_names.append(reader.utf())
            reader.u8()
            reader.i16()
            sub_details.append(reader.utf())

        count = reader.i16()
        counts = [reader.i16() for _ in range(size)]
        self.character.task = TaskState(
            task_id=task_id,
            index=index,
            name=name,
            detail=detail,
            sub_names=sub_names,
            sub_details=sub_details,
            counts=counts,
            count=count,
        )
        self._task_ready.set()

    def _handle_task_update(self, data: bytes) -> None:
        if not self.character.task:
            return
        reader = BufferReader(data)
        self.character.task.count = reader.i16()
        self._task_ready.set()
