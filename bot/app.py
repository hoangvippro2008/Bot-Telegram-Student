from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic

from telegram import BotCommand, BotCommandScopeChat
from telegram.constants import ParseMode
from telegram.error import NetworkError, TelegramError
from telegram.ext import (
    Application,
    ApplicationBuilder,
    CallbackQueryHandler,
    CommandHandler,
    ContextTypes,
    Defaults,
    MessageHandler,
    filters,
)

from bot.config import Config, load_config
from bot.handlers.admin import admin, admin_callback
from bot.handlers.common import (
    help_command,
    ping,
    start,
    text_fallback,
    unknown_command,
    user_id,
)

logger = logging.getLogger(__name__)
_last_network_error = 0.0


def _parse_mode(value: str | None) -> str | None:
    if value is None:
        return None
    if value == "HTML":
        return ParseMode.HTML
    if value == "MARKDOWN":
        return ParseMode.MARKDOWN
    if value == "MARKDOWNV2":
        return ParseMode.MARKDOWN_V2
    raise ValueError(f"Parse mode không hỗ trợ: {value}")


def _logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
        force=True,
    )
    logging.getLogger("httpx").setLevel(logging.WARNING)


async def _post_init(application: Application) -> None:
    commands = [
        BotCommand("start", "Khởi động bot"),
        BotCommand("help", "Xem trợ giúp"),
        BotCommand("ping", "Kiểm tra bot"),
        BotCommand("id", "Xem Telegram ID"),
    ]
    await application.bot.set_my_commands(commands)

    config = application.bot_data.get("config")
    if isinstance(config, Config):
        admin_commands = [*commands, BotCommand("admin", "Bảng quản trị")]
        for admin_id in config.bot.admin_ids:
            try:
                await application.bot.set_my_commands(
                    admin_commands,
                    scope=BotCommandScopeChat(chat_id=admin_id),
                )
            except TelegramError as exc:
                logger.warning(
                    "Không thể đăng ký /admin cho Telegram ID %s: %s",
                    admin_id,
                    exc,
                )

    bot = await application.bot.get_me()
    logger.info("Bot đã kết nối: @%s (%s)", bot.username or "unknown", bot.id)


async def _on_error(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    global _last_network_error

    error = context.error
    if update is None and isinstance(error, NetworkError):
        config = context.application.bot_data.get("config")
        interval = (
            config.network.error_log_interval if isinstance(config, Config) else 60.0
        )
        now = monotonic()
        if interval == 0 or now - _last_network_error >= interval:
            logger.warning(
                "Mất kết nối Telegram: %s. Polling đang tự thử lại.",
                error,
            )
            _last_network_error = now
        return

    logger.error("Lỗi khi xử lý update: %r", update, exc_info=error)


def build(config: Config) -> Application:
    defaults = Defaults(parse_mode=_parse_mode(config.bot.parse_mode))
    application = (
        ApplicationBuilder()
        .token(config.bot.token)
        .defaults(defaults)
        .connect_timeout(config.network.connect_timeout)
        .read_timeout(config.network.read_timeout)
        .get_updates_connect_timeout(config.network.connect_timeout)
        .get_updates_read_timeout(config.network.read_timeout)
        .post_init(_post_init)
        .build()
    )

    application.bot_data["config"] = config
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("help", help_command))
    application.add_handler(CommandHandler("ping", ping))
    application.add_handler(CommandHandler("id", user_id))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))
    application.add_handler(MessageHandler(filters.COMMAND, unknown_command))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, text_fallback))
    application.add_error_handler(_on_error)
    return application


def run(config_path: Path) -> None:
    config = load_config(config_path)
    _logging(config.runtime.log_level)

    allowed_updates = list(config.runtime.allowed_updates)
    if config.bot.admin_ids and "callback_query" not in allowed_updates:
        allowed_updates.append("callback_query")

    logger.info("Đang khởi động bot bằng long polling")
    application = build(config)
    application.run_polling(
        bootstrap_retries=config.runtime.bootstrap_retries,
        drop_pending_updates=config.runtime.drop_pending_updates,
        allowed_updates=allowed_updates,
    )
