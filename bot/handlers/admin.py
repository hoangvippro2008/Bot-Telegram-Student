from __future__ import annotations

import asyncio
import html
from datetime import datetime

import telegram
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatMemberStatus, ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.config import Config
from bot.group import read_group_info
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


def _safe(value: object) -> str:
    return html.escape(str(value))


def _menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("👥 Nhóm người dùng", callback_data="admin:group")],
            [InlineKeyboardButton("📊 Kiểm tra tổng quan", callback_data="admin:check")],
            [
                InlineKeyboardButton("🖥 Hệ thống", callback_data="admin:system"),
                InlineKeyboardButton("🤖 Trạng thái bot", callback_data="admin:bot"),
            ],
            [InlineKeyboardButton("✖️ Đóng", callback_data="admin:close")],
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


def _group_menu(config: Config) -> InlineKeyboardMarkup:
    rows = []
    if config.group.join_url:
        rows.append([InlineKeyboardButton("🔗 Mở nhóm", url=config.group.join_url)])
    rows.append(
        [
            InlineKeyboardButton("🔄 Làm mới", callback_data="admin:group"),
            InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:menu"),
        ]
    )
    return InlineKeyboardMarkup(rows)


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
        "Chọn mục cần quản lý bên dưới."
    )


async def _group_text(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE,
) -> tuple[str, InlineKeyboardMarkup]:
    config = _config(context)
    current_chat = update.effective_chat

    current_hint = ""
    if current_chat and current_chat.type in {ChatType.GROUP, ChatType.SUPERGROUP, ChatType.CHANNEL}:
        current_hint = (
            "\n\n💡 <b>Chat đang mở</b>\n"
            f"ID: <code>{current_chat.id}</code>\n"
            "Có thể dùng ID này cho <code>group.required_chat</code>."
        )

    if not config.group.enabled:
        return (
            "👥 <b>NHÓM NGƯỜI DÙNG</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🔴 <b>Kiểm tra thành viên:</b> Đang tắt\n\n"
            "Bật <code>group.enabled</code> trong <code>config.json</code> "
            "để bắt buộc người dùng tham gia nhóm."
            f"{current_hint}",
            _group_menu(config),
        )

    try:
        info = await read_group_info(context.bot, config.group)
    except TelegramError as exc:
        return (
            "👥 <b>NHÓM NGƯỜI DÙNG</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "🟢 <b>Kiểm tra thành viên:</b> Đang bật\n"
            f"🎯 <b>Nhóm cấu hình:</b> <code>{_safe(config.group.chat_id)}</code>\n\n"
            "⚠️ <b>Chưa đọc được thông tin nhóm.</b>\n"
            f"<code>{_safe(exc)}</code>\n\n"
            "Hãy kiểm tra bot đã được thêm vào nhóm và cấp quyền quản trị."
            f"{current_hint}",
            _group_menu(config),
        )

    bot_role = {
        ChatMemberStatus.OWNER: "Chủ sở hữu",
        ChatMemberStatus.ADMINISTRATOR: "Quản trị viên",
        ChatMemberStatus.MEMBER: "Thành viên",
        ChatMemberStatus.RESTRICTED: "Bị giới hạn",
        ChatMemberStatus.LEFT: "Đã rời nhóm",
        ChatMemberStatus.BANNED: "Bị chặn",
    }.get(info.bot_status, info.bot_status)

    warning = ""
    if not info.bot_is_admin:
        warning = (
            "\n\n⚠️ <b>Cần cấp quyền quản trị cho bot.</b>\n"
            "Telegram chỉ đảm bảo kiểm tra thành viên khác chính xác "
            "khi bot là quản trị viên của nhóm."
        )

    username = f"@{info.username}" if info.username else "Nhóm riêng tư"

    return (
        "👥 <b>NHÓM NGƯỜI DÙNG</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        "🟢 <b>Kiểm tra thành viên:</b> Đang bật\n\n"
        f"🏷 <b>Tên nhóm:</b> {_safe(info.title)}\n"
        f"🆔 <b>Chat ID:</b> <code>{info.chat_id}</code>\n"
        f"🔗 <b>Username:</b> <code>{_safe(username)}</code>\n"
        f"🧩 <b>Loại:</b> <code>{_safe(info.chat_type)}</code>\n"
        f"👤 <b>Thành viên:</b> <code>{info.member_count}</code>\n"
        f"🤖 <b>Quyền bot:</b> {_safe(bot_role)}\n\n"
        "🔒 Người chưa tham gia nhóm sẽ bị chặn trước khi vào chức năng bot."
        f"{warning}{current_hint}\n\n"
        f"🕒 <i>Cập nhật lúc {_updated_at()}</i>",
        _group_menu(config),
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

    if data == "admin:group":
        text, markup = await _group_text(update, context)
        await query.edit_message_text(
            text,
            reply_markup=markup,
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
