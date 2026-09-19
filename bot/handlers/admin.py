from __future__ import annotations

import asyncio
import html
from datetime import datetime

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ParseMode
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
            [
                InlineKeyboardButton(
                    "📊 Kiểm tra tổng quan",
                    callback_data="admin:check",
                )
            ],
            [
                InlineKeyboardButton(
                    "🖥 Hệ thống",
                    callback_data="admin:system",
                ),
                InlineKeyboardButton(
                    "🤖 Trạng thái bot",
                    callback_data="admin:bot",
                ),
            ],
            [
                InlineKeyboardButton(
                    "✖️ Đóng",
                    callback_data="admin:close",
                )
            ],
        ]
    )


def _detail_menu(refresh: str) -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("🔄 Làm mới", callback_data=refresh),
                InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:menu"),
            ]
        ]
    )


def _percent(used: int | None, total: int | None) -> float | None:
    if used is None or total is None or total <= 0:
        return None
    return used / total * 100


def _bar(value: float | None, size: int = 10) -> str:
    if value is None:
        return "░" * size

    value = max(0.0, min(100.0, value))
    filled = round(value / 100 * size)
    return "▰" * filled + "▱" * (size - filled)


def _usage(value: float | None) -> str:
    if value is None:
        return "N/A"
    return f"{value:.1f}%"


def _safe(value: object) -> str:
    return html.escape(str(value))


def _updated_at() -> str:
    return datetime.now().strftime("%H:%M:%S")


def _system_text(stats) -> str:
    ram_used = (
        stats.ram_total - stats.ram_available
        if stats.ram_total is not None and stats.ram_available is not None
        else None
    )
    ram_percent = _percent(ram_used, stats.ram_total)
    disk_percent = _percent(stats.disk_used, stats.disk_total)
    cpu_percent = stats.cpu_percent
    load = (
        " / ".join(f"{value:.2f}" for value in stats.load_average)
        if stats.load_average
        else "N/A"
    )

    return (
        "🖥 <b>THÔNG TIN HỆ THỐNG</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🏷 <b>Host:</b> <code>{_safe(stats.hostname)}</code>\n"
        f"💻 <b>Hệ điều hành:</b> {_safe(stats.os_name)} {_safe(stats.os_release)}\n"
        f"🧩 <b>Kiến trúc:</b> <code>{_safe(stats.architecture)}</code>\n\n"
        "⚙️ <b>CPU</b>\n"
        f"└ {_safe(stats.cpu_name)}\n"
        f"   {_bar(cpu_percent)}  <b>{_usage(cpu_percent)}</b>\n"
        f"   Luồng CPU: <code>{stats.cpu_count}</code> · "
        f"Python: <code>{stats.threads}</code>\n"
        f"   Load: <code>{_safe(load)}</code>\n\n"
        "🧠 <b>RAM</b>\n"
        f"   {_bar(ram_percent)}  <b>{_usage(ram_percent)}</b>\n"
        f"   Dùng: <code>{format_bytes(ram_used)}</code> / "
        f"<code>{format_bytes(stats.ram_total)}</code>\n"
        f"   Trống: <code>{format_bytes(stats.ram_available)}</code>\n"
        f"   Bot: <code>{format_bytes(stats.process_ram)}</code>\n\n"
        "💾 <b>Ổ đĩa</b>\n"
        f"   {_bar(disk_percent)}  <b>{_usage(disk_percent)}</b>\n"
        f"   Dùng: <code>{format_bytes(stats.disk_used)}</code> / "
        f"<code>{format_bytes(stats.disk_total)}</code>\n"
        f"   Trống: <code>{format_bytes(stats.disk_free)}</code>\n\n"
        "🐍 <b>Tiến trình</b>\n"
        f"   Python: <code>{_safe(stats.python_version)}</code>\n"
        f"   PID: <code>{stats.pid}</code>\n\n"
        f"🕒 <i>Cập nhật lúc {_updated_at()}</i>"
    )


def _bot_text(context: ContextTypes.DEFAULT_TYPE) -> str:
    config = _config(context)
    bot = context.bot
    username = f"@{bot.username}" if bot.username else "N/A"

    return (
        "🤖 <b>TRẠNG THÁI BOT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🟢 <b>Online</b>\n\n"
        f"👤 <b>Username:</b> <code>{_safe(username)}</code>\n"
        f"🆔 <b>Bot ID:</b> <code>{bot.id}</code>\n"
        f"⏱ <b>Uptime:</b> <code>{format_duration(process_uptime())}</code>\n"
        f"👑 <b>Quản trị viên:</b> <code>{len(config.bot.admin_ids)}</code>\n"
        f"📥 <b>Update chờ:</b> <code>{context.application.update_queue.qsize()}</code>\n"
        f"📦 <b>PTB:</b> <code>{_safe(telegram.__version__)}</code>\n\n"
        f"🕒 <i>Cập nhật lúc {_updated_at()}</i>"
    )


def _overview_text(context: ContextTypes.DEFAULT_TYPE, stats) -> str:
    ram_used = (
        stats.ram_total - stats.ram_available
        if stats.ram_total is not None and stats.ram_available is not None
        else None
    )
    ram_percent = _percent(ram_used, stats.ram_total)
    disk_percent = _percent(stats.disk_used, stats.disk_total)
    cpu_percent = stats.cpu_percent
    bot = context.bot
    username = f"@{bot.username}" if bot.username else "N/A"

    return (
        "✨ <b>TỔNG QUAN QUẢN TRỊ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🤖 <b>Bot:</b> <code>{_safe(username)}</code> · 🟢 Online\n"
        f"⏱ <b>Uptime:</b> <code>{format_duration(process_uptime())}</code>\n\n"
        "⚙️ <b>CPU</b>\n"
        f"   {_bar(cpu_percent)}  <b>{_usage(cpu_percent)}</b>\n"
        f"   <code>{stats.cpu_count}</code> luồng logic\n\n"
        "🧠 <b>RAM</b>\n"
        f"   {_bar(ram_percent)}  <b>{_usage(ram_percent)}</b>\n"
        f"   <code>{format_bytes(ram_used)}</code> / "
        f"<code>{format_bytes(stats.ram_total)}</code>\n\n"
        "💾 <b>Ổ đĩa</b>\n"
        f"   {_bar(disk_percent)}  <b>{_usage(disk_percent)}</b>\n"
        f"   Còn <code>{format_bytes(stats.disk_free)}</code>\n\n"
        f"🕒 <i>Cập nhật lúc {_updated_at()}</i>"
    )


def _menu_text(update: Update) -> str:
    user = update.effective_user
    name = _safe(user.full_name) if user else "Admin"

    return (
        "🌿 <b>BẢNG QUẢN TRỊ</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"Xin chào <b>{name}</b> 👋\n\n"
        "Chọn mục cần kiểm tra bên dưới."
    )


async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    if not _is_admin(update, context) or not update.effective_message:
        return

    await update.effective_message.reply_text(
        _menu_text(update),
        reply_markup=_menu(),
        parse_mode=ParseMode.HTML,
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
            _menu_text(update),
            reply_markup=_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "admin:close":
        await query.edit_message_text(
            "✅ <b>Đã đóng bảng quản trị.</b>",
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "admin:bot":
        await query.edit_message_text(
            _bot_text(context),
            reply_markup=_detail_menu("admin:bot"),
            parse_mode=ParseMode.HTML,
        )
        return

    if data in {"admin:system", "admin:check"}:
        stats = await asyncio.to_thread(read_system_stats)

        if data == "admin:system":
            text = _system_text(stats)
            refresh = "admin:system"
        else:
            text = _overview_text(context, stats)
            refresh = "admin:check"

        await query.edit_message_text(
            text,
            reply_markup=_detail_menu(refresh),
            parse_mode=ParseMode.HTML,
        )
