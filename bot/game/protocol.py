from __future__ import annotations

import asyncio
import struct
from dataclasses import dataclass


_SPECIAL_COMMANDS = {-32, -66, 11, -67, -74, -87, 66, 12}


def _signed(value: int) -> int:
    return value if value < 128 else value - 256


@dataclass(frozen=True)
class Packet:
    command: int
    data: bytes


class BufferReader:
    def __init__(self, data: bytes):
        self.data = data
        self.pos = 0

    @property
    def remaining(self) -> int:
        return len(self.data) - self.pos

    def _take(self, size: int) -> bytes:
        end = self.pos + size
        if size < 0 or end > len(self.data):
            raise ValueError("Packet thiếu dữ liệu")
        value = self.data[self.pos:end]
        self.pos = end
        return value

    def u8(self) -> int:
        return self._take(1)[0]

    def i8(self) -> int:
        return struct.unpack(">b", self._take(1))[0]

    def i16(self) -> int:
        return struct.unpack(">h", self._take(2))[0]

    def u16(self) -> int:
        return struct.unpack(">H", self._take(2))[0]

    def i32(self) -> int:
        return struct.unpack(">i", self._take(4))[0]

    def i64(self) -> int:
        return struct.unpack(">q", self._take(8))[0]

    def utf(self) -> str:
        size = self.u16()
        return self._take(size).decode("utf-8", errors="replace")

    def bytes(self, size: int) -> bytes:
        return self._take(size)


class BufferWriter:
    def __init__(self):
        self.data = bytearray()

    def u8(self, value: int) -> BufferWriter:
        self.data.append(value & 0xFF)
        return self

    def boolean(self, value: bool) -> BufferWriter:
        return self.u8(1 if value else 0)

    def i16(self, value: int) -> BufferWriter:
        self.data.extend(struct.pack(">h", value))
        return self

    def i32(self, value: int) -> BufferWriter:
        self.data.extend(struct.pack(">i", value))
        return self

    def i64(self, value: int) -> BufferWriter:
        self.data.extend(struct.pack(">q", value))
        return self

    def utf(self, value: str) -> BufferWriter:
        raw = value.encode("utf-8")
        if len(raw) > 32767:
            raise ValueError("Chuỗi UTF quá dài")
        self.data.extend(struct.pack(">H", len(raw)))
        self.data.extend(raw)
        return self

    def build(self) -> bytes:
        return bytes(self.data)


class GameProtocol:
    def __init__(self):
        self.key: bytearray | None = None
        self.read_pos = 0
        self.write_pos = 0

    @property
    def encrypted(self) -> bool:
        return bool(self.key)

    def set_key(self, raw: bytes) -> None:
        if not raw:
            raise ValueError("Server trả key rỗng")

        key = bytearray(raw)
        for index in range(len(key) - 1):
            key[index + 1] ^= key[index]

        self.key = key
        self.read_pos = 0
        self.write_pos = 0

    def _read_key(self, value: int) -> int:
        if not self.key:
            return value & 0xFF
        result = (value & 0xFF) ^ self.key[self.read_pos]
        self.read_pos = (self.read_pos + 1) % len(self.key)
        return result & 0xFF

    def _write_key(self, value: int) -> int:
        if not self.key:
            return value & 0xFF
        result = (value & 0xFF) ^ self.key[self.write_pos]
        self.write_pos = (self.write_pos + 1) % len(self.key)
        return result & 0xFF

    async def read_packet(self, reader: asyncio.StreamReader) -> Packet:
        raw_command = (await reader.readexactly(1))[0]
        command_byte = self._read_key(raw_command) if self.encrypted else raw_command
        command = _signed(command_byte)

        if command in _SPECIAL_COMMANDS and self.encrypted:
            length_bytes = await reader.readexactly(3)
            a = _signed(self._read_key(length_bytes[0])) + 128
            b = _signed(self._read_key(length_bytes[1])) + 128
            c = _signed(self._read_key(length_bytes[2])) + 128
            size = (c * 256 + b) * 256 + a
        else:
            length_bytes = await reader.readexactly(2)
            if self.encrypted:
                high = self._read_key(length_bytes[0])
                low = self._read_key(length_bytes[1])
            else:
                high, low = length_bytes
            size = ((high & 0xFF) << 8) | (low & 0xFF)

        if size < 0 or size > 8 * 1024 * 1024:
            raise ValueError(f"Packet size không hợp lệ: {size}")

        payload = bytearray(await reader.readexactly(size))
        if self.encrypted:
            for index, value in enumerate(payload):
                payload[index] = self._read_key(value)

        return Packet(command=command, data=bytes(payload))

    def encode_packet(self, command: int, payload: bytes = b"") -> bytes:
        if len(payload) > 65535:
            raise ValueError("Packet gửi quá lớn")

        command_byte = command & 0xFF
        size = len(payload)

        if not self.encrypted:
            return bytes((command_byte, (size >> 8) & 0xFF, size & 0xFF)) + payload

        output = bytearray()
        output.append(self._write_key(command_byte))
        output.append(self._write_key((size >> 8) & 0xFF))
        output.append(self._write_key(size & 0xFF))
        output.extend(self._write_key(value) for value in payload)
        return bytes(output)
