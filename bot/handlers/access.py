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


async def _send_locked(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
    error: bool = False,
) -> None:
    config = _config(context)
    text = _locked_text()
    if error:
        text = (
            "⚠️ <b>CHƯA THỂ KIỂM TRA THÀNH VIÊN</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Bot chưa xác minh được trạng thái trong nhóm. "
            "Bạn có thể thử lại sau."
        )

    query = update.callback_query
    if query is not None:
        await query.answer()
        if query.message:
            await query.message.reply_text(
                text,
                reply_markup=_join_markup(config.group),
                parse_mode=ParseMode.HTML,
            )
        return

    if update.effective_message:
        await update.effective_message.reply_text(
            text,
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

    try:
        if await has_membership(context.bot, config.group, user.id):
            return
    except TelegramError as exc:
        logger.warning("Không thể kiểm tra thành viên %s: %s", user.id, exc)
        await _send_locked(update, context, error=True)
        raise ApplicationHandlerStop

    await _send_locked(update, context)
    raise ApplicationHandlerStop


async def check_access(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    config = _config(context)

    if query is None or user is None:
        return

    try:
        allowed = await has_membership(context.bot, config.group, user.id)
    except TelegramError as exc:
        logger.warning("Không thể kiểm tra lại thành viên %s: %s", user.id, exc)
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
