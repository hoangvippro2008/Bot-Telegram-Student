from __future__ import annotations

from telegram import Update
from telegram.ext import ContextTypes

from bot.config import Config


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    config = context.application.bot_data.get("config")
    if not isinstance(config, Config):
        raise RuntimeError("Bot config chưa được khởi tạo")
    return config


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(_config(context).messages.start)


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(_config(context).messages.help)


async def ping(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if update.effective_message:
        await update.effective_message.reply_text("Pong.")


async def user_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not update.effective_message:
        return

    user_id_value = update.effective_user.id if update.effective_user else "N/A"
    chat_id_value = update.effective_chat.id if update.effective_chat else "N/A"
    await update.effective_message.reply_text(
        f"User ID: {user_id_value}\nChat ID: {chat_id_value}"
    )


async def unknown_command(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(
            _config(context).messages.unknown_command
        )


async def text_fallback(
    update: Update, context: ContextTypes.DEFAULT_TYPE
) -> None:
    if update.effective_message:
        await update.effective_message.reply_text(_config(context).messages.text_fallback)
