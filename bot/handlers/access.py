from __future__ import annotations

import logging

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
from telegram.error import TelegramError
from telegram.ext import ApplicationHandlerStop, ContextTypes

from bot.config import Config, GroupConfig
from bot.group import has_membership


logger = logging.getLogger(__name__)


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    config = context.application.bot_data.get("config")
    if not isinstance(config, Config):
        raise RuntimeError("Bot config chưa được khởi tạo")
    return config


def _is_admin(update: Update, config: Config) -> bool:
    user = update.effective_user
    return bool(user and user.id in config.bot.admin_ids)


def _group_ready(context: ContextTypes.DEFAULT_TYPE) -> bool:
    return context.application.bot_data.get("group_ready") is True


def _join_markup(group: GroupConfig) -> InlineKeyboardMarkup:
    rows = []
    if group.join_url:
        rows.append(
            [InlineKeyboardButton("🌿 Tham gia nhóm", url=group.join_url)]
        )
    rows.append(
        [InlineKeyboardButton("✅ Tôi đã tham gia", callback_data="access:check")]
    )
    return InlineKeyboardMarkup(rows)


def _locked_text() -> str:
    return (
        "🔒 <b>CHƯA XÁC MINH THÀNH VIÊN</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Bạn cần tham gia nhóm của bot trước khi sử dụng.\n\n"
        "1. Bấm <b>Tham gia nhóm</b>\n"
        "2. Tham gia nhóm Telegram\n"
        "3. Quay lại và bấm <b>Tôi đã tham gia</b>"
    )


def _unavailable_text() -> str:
    return (
        "🛠 <b>HỆ THỐNG XÁC MINH CHƯA SẴN SÀNG</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Bot hiện chưa truy cập được nhóm bắt buộc.\n"
        "Vui lòng thử lại sau hoặc liên hệ quản trị viên."
    )


async def _send_locked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    config = _config(context)

    if update.effective_message:
        await update.effective_message.reply_text(
            _locked_text(),
            reply_markup=_join_markup(config.group),
            parse_mode=ParseMode.HTML,
        )


async def _send_unavailable(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> None:
    config = _config(context)

    if update.effective_message:
        await update.effective_message.reply_text(
            _unavailable_text(),
            reply_markup=_join_markup(config.group),
            parse_mode=ParseMode.HTML,
        )


async def access_guard(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    config = _config(context)
    user = update.effective_user

    if not config.group.enabled or user is None or _is_admin(update, config):
        return

    query = update.callback_query
    if query is not None and query.data == "access:check":
        return

    if not _group_ready(context):
        await _send_unavailable(update, context)
        raise ApplicationHandlerStop

    try:
        if await has_membership(context.bot, config.group, user.id):
            return
    except TelegramError as exc:
        logger.warning("Lỗi mạng khi kiểm tra thành viên %s: %s", user.id, exc)
        await _send_unavailable(update, context)
        raise ApplicationHandlerStop

    await _send_locked(update, context)
    raise ApplicationHandlerStop


async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    config = _config(context)

    if query is None or user is None:
        return

    if user.id in config.bot.admin_ids:
        await query.answer("Quản trị viên không cần xác minh.", show_alert=True)
        return

    if not _group_ready(context):
        await query.answer(
            "Nhóm xác minh chưa sẵn sàng. Hãy liên hệ quản trị viên.",
            show_alert=True,
        )
        return

    try:
        allowed = await has_membership(context.bot, config.group, user.id)
    except TelegramError as exc:
        logger.warning("Lỗi mạng khi kiểm tra lại thành viên %s: %s", user.id, exc)
        await query.answer(
            "Chưa thể kiểm tra thành viên lúc này.",
            show_alert=True,
        )
        return

    if not allowed:
        await query.answer(
            "Bạn chưa tham gia nhóm. Hãy vào nhóm rồi thử lại.",
            show_alert=True,
        )
        return

    await query.answer("Xác minh thành công.")

    buttons = []
    if context.bot.username:
        buttons.append(
            [
                InlineKeyboardButton(
                    "▶️ Bắt đầu sử dụng",
                    url=f"https://t.me/{context.bot.username}?start=member",
                )
            ]
        )

    await query.edit_message_text(
        "✅ <b>XÁC MINH THÀNH CÔNG</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "Bạn đã tham gia nhóm và có thể sử dụng bot.",
        reply_markup=InlineKeyboardMarkup(buttons) if buttons else None,
        parse_mode=ParseMode.HTML,
    )
