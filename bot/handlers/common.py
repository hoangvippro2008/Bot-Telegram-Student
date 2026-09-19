from __future__ import annotations

import html

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from bot.config import Config


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    config = context.application.bot_data.get("config")
    if not isinstance(config, Config):
        raise RuntimeError("Bot config chưa được khởi tạo")
    return config


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return

    config = _config(context)
    user = update.effective_user
    name = html.escape(user.full_name) if user else "bạn"

    text = (
        "🌿 <b>BOT TELEGRAM STUDENT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Xin chào <b>{name}</b> 👋\n\n"
        "✅ Bạn đã được xác minh và bot đã sẵn sàng."
    )

    if user and user.id in config.bot.admin_ids:
        text += "\n\n👑 <b>Vai trò:</b> Quản trị viên\nDùng /admin để mở bảng quản trị."

    await update.effective_message.reply_text(text, parse_mode=ParseMode.HTML)
