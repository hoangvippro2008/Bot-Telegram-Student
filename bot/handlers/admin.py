from __future__ import annotations

import asyncio

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.ext import ContextTypes

from bot.config import Config
from bot.system import (
    format_bytes,
    format_duration,
    process_uptime,
    read_system_stats,
)


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    config = context.application.bot_data.get("config")
    if not isinstance(config, Config):
        raise RuntimeError("Bot config chưa được khởi tạo")
    return config


def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return bool(user and user.id in _config(context).bot.admin_ids)


def _menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Kiểm tra thông tin", callback_data="admin:check")],
            [
                InlineKeyboardButton("Thông tin hệ thống", callback_data="admin:system"),
                InlineKeyboardButton("Trạng thái bot", callback_data="admin:bot"),
            ],
            [InlineKeyboardButton("Đóng", callback_data="admin:close")],
        ]
    )


def _detail_menu(refresh: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("Làm mới", callback_data=refresh)],
            [InlineKeyboardButton("Quay lại", callback_data="admin:menu")],
        ]
    )


def _percent(used: int | None, total: int | None) -> str:
    if used is None or total is None or total <= 0:
        return "N/A"
    return f"{used / total * 100:.1f}%"


def _system_text(stats) -> str:
    ram_used = (
        stats.ram_total - stats.ram_available
        if stats.ram_total is not None and stats.ram_available is not None
        else None
    )
    load = (
        " / ".join(f"{value:.2f}" for value in stats.load_average)
        if stats.load_average
        else "N/A"
    )
    cpu = f"{stats.cpu_percent:.1f}%" if stats.cpu_percent is not None else "N/A"

    return (
        "THÔNG TIN HỆ THỐNG\n\n"
        f"Host: {stats.hostname}\n"
        f"OS: {stats.os_name} {stats.os_release}\n"
        f"Kiến trúc: {stats.architecture}\n"
        f"CPU: {stats.cpu_name}\n"
        f"CPU sử dụng: {cpu}\n"
        f"CPU logic: {stats.cpu_count}\n"
        f"Threads Python: {stats.threads}\n"
        f"Load avg: {load}\n\n"
        "RAM\n"
        f"Đang dùng: {format_bytes(ram_used)} / {format_bytes(stats.ram_total)}"
        f" ({_percent(ram_used, stats.ram_total)})\n"
        f"Còn trống: {format_bytes(stats.ram_available)}\n"
        f"Bot process: {format_bytes(stats.process_ram)}\n\n"
        "Ổ ĐĨA\n"
        f"Đang dùng: {format_bytes(stats.disk_used)} / {format_bytes(stats.disk_total)}"
        f" ({_percent(stats.disk_used, stats.disk_total)})\n"
        f"Còn trống: {format_bytes(stats.disk_free)}\n\n"
        f"Python: {stats.python_version}\n"
        f"PID: {stats.pid}"
    )


def _bot_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    config = _config(context)
    bot = context.bot
    username = f"@{bot.username}" if bot.username else "N/A"

    return (
        "TRẠNG THÁI BOT\n\n"
        "Trạng thái: Online\n"
        f"Username: {username}\n"
        f"Bot ID: {bot.id}\n"
        f"Uptime: {format_duration(process_uptime())}\n"
        f"Admin: {len(config.bot.admin_ids)}\n"
        f"Update queue: {context.application.update_queue.qsize()}\n"
        f"python-telegram-bot: {telegram.__version__}"
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update, context) or not update.effective_message:
        return

    await update.effective_message.reply_text(
        "BẢNG QUẢN TRỊ\n\nChọn chức năng:",
        reply_markup=_menu(),
        parse_mode=None,
    )


async def admin_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    if query is None:
        return

    if not _is_admin(update, context):
        await query.answer("Bạn không có quyền truy cập.", show_alert=True)
        return

    data = query.data if isinstance(query.data, str) else ""
    await query.answer()

    if data == "admin:menu":
        await query.edit_message_text(
            "BẢNG QUẢN TRỊ\n\nChọn chức năng:",
            reply_markup=_menu(),
            parse_mode=None,
        )
        return

    if data == "admin:close":
        await query.edit_message_text("Đã đóng bảng quản trị.", parse_mode=None)
        return

    if data == "admin:bot":
        await query.edit_message_text(
            _bot_text(context),
            reply_markup=_detail_menu("admin:bot"),
            parse_mode=None,
        )
        return

    if data in {"admin:system", "admin:check"}:
        stats = await asyncio.to_thread(read_system_stats)

        if data == "admin:system":
            text = _system_text(stats)
            refresh = "admin:system"
        else:
            text = (
                "KIỂM TRA THÔNG TIN\n\n"
                f"{_bot_text(context)}\n\n"
                f"{_system_text(stats)}"
            )
            refresh = "admin:check"

        await query.edit_message_text(
            text,
            reply_markup=_detail_menu(refresh),
            parse_mode=None,
        )
