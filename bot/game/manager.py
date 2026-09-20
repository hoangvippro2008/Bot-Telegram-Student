from __future__ import annotations

from dataclasses import dataclass

from bot.game.client import GameClient
from bot.game.server import GameServer


@dataclass
class GameProfile:
    account: str | None = None
    password: str | None = None
    server: GameServer | None = None
    client: GameClient | None = None
    input_mode: str | None = None

    @property
    def password_set(self) -> bool:
        return bool(self.password)


class GameManager:
    def __init__(self):
        self._profiles: dict[int, GameProfile] = {}

    def get(self, user_id: int) -> GameProfile:
        profile = self._profiles.get(user_id)
        if profile is None:
            profile = GameProfile()
            self._profiles[user_id] = profile
        return profile

    async def connect(self, user_id: int) -> GameClient:
        profile = self.get(user_id)
        if not profile.account:
            raise ValueError("Chưa nhập tài khoản")
        if not profile.password:
            raise ValueError("Chưa nhập mật khẩu")
        if not profile.server:
            raise ValueError("Chưa chọn máy chủ")

        if profile.client:
            await profile.client.disconnect()

        client = GameClient(profile.server, profile.account, profile.password)
        profile.client = client
        await client.connect()
        return client

    async def disconnect(self, user_id: int) -> None:
        profile = self.get(user_id)
        if profile.client:
            await profile.client.disconnect()
            profile.client = None

    async def close_all(self) -> None:
        for profile in list(self._profiles.values()):
            if profile.client:
                await profile.client.disconnect()
                profile.client = None
