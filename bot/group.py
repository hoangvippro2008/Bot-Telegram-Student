from __future__ import annotations

from dataclasses import dataclass

from telegram import Bot, ChatMember
from telegram.constants import ChatMemberStatus
from telegram.error import TelegramError

from bot.config import GroupConfig


_ACTIVE = {
    ChatMemberStatus.OWNER,
    ChatMemberStatus.ADMINISTRATOR,
    ChatMemberStatus.MEMBER,
}


@dataclass(frozen=True)
class GroupInfo:
    title: str
    chat_id: int
    chat_type: str
    username: str | None
    member_count: int
    bot_status: str
    bot_is_admin: bool


@dataclass(frozen=True)
class GroupCheck:
    ready: bool
    info: GroupInfo | None
    error: str | None


def is_active_member(member: ChatMember) -> bool:
    if member.status in _ACTIVE:
        return True
    if member.status == ChatMemberStatus.RESTRICTED:
        return bool(getattr(member, "is_member", False))
    return False


async def has_membership(bot: Bot, group: GroupConfig, user_id: int) -> bool:
    if not group.enabled or group.chat_id is None:
        return True

    member = await bot.get_chat_member(group.chat_id, user_id)
    return is_active_member(member)


async def read_group_info(bot: Bot, group: GroupConfig) -> GroupInfo:
    if not group.enabled or group.chat_id is None:
        raise RuntimeError("Chưa bật kiểm tra nhóm")

    chat = await bot.get_chat(group.chat_id)
    member_count = await bot.get_chat_member_count(group.chat_id)
    bot_member = await bot.get_chat_member(group.chat_id, bot.id)

    return GroupInfo(
        title=chat.title or "Không có tên",
        chat_id=chat.id,
        chat_type=chat.type,
        username=chat.username,
        member_count=member_count,
        bot_status=bot_member.status,
        bot_is_admin=bot_member.status
        in {ChatMemberStatus.OWNER, ChatMemberStatus.ADMINISTRATOR},
    )


async def check_group(bot: Bot, group: GroupConfig) -> GroupCheck:
    if not group.enabled:
        return GroupCheck(ready=True, info=None, error=None)

    try:
        info = await read_group_info(bot, group)
    except TelegramError as exc:
        return GroupCheck(ready=False, info=None, error=str(exc))

    if not info.bot_is_admin:
        return GroupCheck(
            ready=False,
            info=info,
            error="Bot chưa có quyền quản trị trong nhóm",
        )

    return GroupCheck(ready=True, info=info, error=None)
