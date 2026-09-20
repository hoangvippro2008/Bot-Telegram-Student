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


@dataclass(frozen=True)
class CharacterChoice:
    player_id: int
    name: str
    head: int
    body: int
    leg: int
    power: int


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
        self.characters: list[CharacterChoice] = []
        self.character = CharacterState()
        self.status = "Chưa kết nối"
        self.error: str | None = None
        self.connected_at: float | None = None
        self._handshake = asyncio.Event()
        self._characters = asyncio.Event()
        self._character_ready = asyncio.Event()
        self._task_ready = asyncio.Event()
        self._write_lock = asyncio.Lock()
        self._received_commands: list[int] = []
        self._finish_update_sent = False

    @property
    def connected(self) -> bool:
        return self.writer is not None and not self.writer.is_closing() and self.error is None

    @property
    def uptime(self) -> float:
        if self.connected_at is None:
            return 0.0
        return max(0.0, monotonic() - self.connected_at)

    async def connect(self) -> None:
        await self.disconnect()
        self.protocol = GameProtocol()
        self.characters.clear()
        self.character = CharacterState()
        self.error = None
        self._handshake = asyncio.Event()
        self._characters = asyncio.Event()
        self._character_ready = asyncio.Event()
        self._task_ready = asyncio.Event()
        self._received_commands.clear()
        self._finish_update_sent = False
        self.status = "Đang kết nối"

        try:
            self.reader, self.writer = await asyncio.wait_for(
                asyncio.open_connection(self.server.host, self.server.port),
                timeout=self.connect_timeout,
            )
            self.connected_at = monotonic()
            self.reader_task = asyncio.create_task(self._read_loop())

            await self._send(-27, b"")
            await self._wait(self._handshake, 6.0, "Không nhận được key từ máy chủ")

            self.status = "Đang đăng nhập"
            await self._send_client_info()
            await self._send_login()
            await self._wait(
                self._characters,
                15.0,
                "Không nhận được PlayerData sau đăng nhập",
            )

            if not self.characters:
                raise RuntimeError("Tài khoản chưa có nhân vật trên máy chủ này")

            self.status = "Đang vào nhân vật"
            await self._enter_character(self.characters[0].player_id)
            await self._wait(
                self._character_ready,
                12.0,
                "Đã đăng nhập nhưng chưa nhận được dữ liệu nhân vật",
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

    async def _enter_character(self, player_id: int) -> None:
        payload = BufferWriter().i32(player_id).build()
        await self._send(-38, payload)

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
            self._characters.set()
            self._character_ready.set()
            self._task_ready.set()

    async def _handle(self, packet: Packet) -> None:
        if packet.command == -27:
            self._handle_key(packet.data)
            return
        if packet.command == 0:
            self._handle_character_list(packet.data)
            return
        if packet.command == -28:
            await self._handle_not_map(packet.data)
            return
        if packet.command == -30:
            self._handle_subcommand(packet.data)
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

        if subcommand != 4 or self._finish_update_sent:
            return

        self._finish_update_sent = True
        self.status = "Đang hoàn tất cập nhật"
        logger.info("Game login: nhận -28/4, gửi -38 hoàn tất cập nhật")
        await self._send(-38, b"")

    def _handle_key(self, data: bytes) -> None:
        reader = BufferReader(data)
        size = reader.u8()
        self.protocol.set_key(reader.bytes(size))
        if reader.remaining >= 2:
            try:
                reader.utf()
                if reader.remaining >= 4:
                    reader.i32()
                if reader.remaining:
                    reader.u8()
            except ValueError:
                pass
        self._handshake.set()

    def _handle_character_list(self, data: bytes) -> None:
        reader = BufferReader(data)
        count = reader.u8()
        characters: list[CharacterChoice] = []
        for _ in range(count):
            characters.append(
                CharacterChoice(
                    player_id=reader.i32(),
                    name=reader.utf(),
                    head=reader.i16(),
                    body=reader.i16(),
                    leg=reader.i16(),
                    power=reader.i64(),
                )
            )
        self.characters = characters
        logger.info("Game login: nhận PlayerData, số nhân vật=%s", len(characters))
        self._characters.set()

    def _handle_subcommand(self, data: bytes) -> None:
        reader = BufferReader(data)
        if not reader.remaining:
            return
        subcommand = reader.u8()
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
        self._character_ready.set()

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
