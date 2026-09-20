from __future__ import annotations

import logging
from pathlib import Path
from time import monotonic

from telegram import BotCommand, BotCommandScopeChat, Update
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
    TypeHandler,
    filters,
)

from bot.config import Config, load_config
from bot.game.manager import GameManager
from bot.group import check_group
from bot.handlers.access import access_guard, check_access
from bot.handlers.admin import admin, admin_callback
from bot.handlers.admin_boss import boss_callback, boss_input
from bot.handlers.common import start

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


async def _check_required_group(application: Application, config: Config) -> None:
    result = await check_group(application.bot, config.group)
    application.bot_data["group_ready"] = result.ready
    application.bot_data["group_error"] = result.error

    if not config.group.enabled:
        logger.info("Kiểm tra thành viên nhóm đang tắt")
        return

    if result.ready and result.info:
        logger.info(
            "Nhóm bắt buộc hợp lệ: %s (%s) | %s thành viên",
            result.info.title,
            result.info.chat_id,
            result.info.member_count,
        )
        return

    logger.error(
        "Nhóm bắt buộc chưa sẵn sàng: %s | %s",
        config.group.chat_id,
        result.error or "Không xác định được lỗi",
    )


async def _post_init(application: Application) -> None:
    member_commands = [BotCommand("start", "Bắt đầu")]
    await application.bot.set_my_commands(member_commands)

    config = application.bot_data.get("config")
    if isinstance(config, Config):
        admin_commands = [
            BotCommand("start", "Bắt đầu"),
            BotCommand("admin", "Bảng quản trị"),
        ]
        for admin_id in config.bot.admin_ids:
            try:
                await application.bot.set_my_commands(
                    admin_commands,
                    scope=BotCommandScopeChat(chat_id=admin_id),
                )
            except TelegramError as exc:
                logger.warning(
                    "Không thể đăng ký lệnh admin cho Telegram ID %s: %s",
                    admin_id,
                    exc,
                )

    bot = await application.bot.get_me()
    logger.info("Bot đã kết nối: @%s (%s)", bot.username or "unknown", bot.id)

    if isinstance(config, Config):
        await _check_required_group(application, config)


async def _post_shutdown(application: Application) -> None:
    manager = application.bot_data.get("game_manager")
    if isinstance(manager, GameManager):
        await manager.close_all()


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
        .post_shutdown(_post_shutdown)
        .build()
    )

    application.bot_data["config"] = config
    application.bot_data["group_ready"] = not config.group.enabled
    application.bot_data["group_error"] = None
    application.bot_data["game_manager"] = GameManager()

    application.add_handler(TypeHandler(Update, access_guard), group=-1)

    application.add_handler(CallbackQueryHandler(check_access, pattern=r"^access:check$"))
    application.add_handler(CommandHandler("start", start))
    application.add_handler(CommandHandler("admin", admin))
    application.add_handler(CallbackQueryHandler(boss_callback, pattern=r"^boss:"))
    application.add_handler(CallbackQueryHandler(admin_callback, pattern=r"^admin:"))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, boss_input))

    application.add_error_handler(_on_error)
    return application


def run(config_path: Path) -> None:
    config = load_config(config_path)
    _logging(config.runtime.log_level)

    allowed_updates = list(config.runtime.allowed_updates)
    if (config.bot.admin_ids or config.group.enabled) and "callback_query" not in allowed_updates:
        allowed_updates.append("callback_query")

    logger.info("Đang khởi động bot bằng long polling")
    application = build(config)
    application.run_polling(
        bootstrap_retries=config.runtime.bootstrap_retries,
        drop_pending_updates=config.runtime.drop_pending_updates,
        allowed_updates=allowed_updates,
    )
