from __future__ import annotations

import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import TelegramError
from telegram.ext import ContextTypes

from bot.config import Config
from bot.game.manager import GameManager, GameProfile
from bot.game.server import GameServer, list_servers
from bot.system import format_duration


def _config(context: ContextTypes.DEFAULT_TYPE) -> Config:
    config = context.application.bot_data.get("config")
    if not isinstance(config, Config):
        raise RuntimeError("Bot config chưa được khởi tạo")
    return config


def _manager(context: ContextTypes.DEFAULT_TYPE) -> GameManager:
    manager = context.application.bot_data.get("game_manager")
    if not isinstance(manager, GameManager):
        raise RuntimeError("Game manager chưa được khởi tạo")
    return manager


def _is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    user = update.effective_user
    return bool(user and user.id in _config(context).bot.admin_ids)


def _safe(value: object) -> str:
    return html.escape(str(value))


def _num(value: int | None) -> str:
    if value is None:
        return "Chưa nhận"
    return f"{value:,}".replace(",", ".")


def _menu(profile: GameProfile) -> InlineKeyboardMarkup:
    connected = bool(profile.client and profile.client.connected)
    connect_label = "⛔ Ngắt kết nối" if connected else "🔌 Kết nối máy chủ"
    connect_data = "boss:disconnect" if connected else "boss:connect"
    return InlineKeyboardMarkup(
        [
            [
                InlineKeyboardButton("👤 Tài khoản", callback_data="boss:account"),
                InlineKeyboardButton("🔑 Mật khẩu", callback_data="boss:password"),
            ],
            [InlineKeyboardButton("🌐 Chọn máy chủ", callback_data="boss:servers")],
            [InlineKeyboardButton(connect_label, callback_data=connect_data)],
            [InlineKeyboardButton("📋 Thông tin nhân vật", callback_data="boss:character")],
            [InlineKeyboardButton("🔎 Kiểm tra thông báo Boss", callback_data="boss:check")],
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="admin:menu")],
        ]
    )


def _boss_text(profile: GameProfile) -> str:
    client = profile.client
    if client and client.connected:
        status = "🟢 Đã kết nối"
    elif client and client.error:
        status = f"🔴 {client.status}"
    else:
        status = "⚪ Chưa kết nối"

    account = _safe(profile.account) if profile.account else "Chưa cấu hình"
    password = "Đã cấu hình" if profile.password_set else "Chưa cấu hình"
    server = _safe(profile.server.name) if profile.server else "Chưa chọn"

    return (
        "🔔 <b>QUẢN LÝ THÔNG BÁO BOSS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔌 <b>Trạng thái:</b> {status}\n"
        f"👤 <b>Tài khoản:</b> <code>{account}</code>\n"
        f"🔑 <b>Mật khẩu:</b> {password}\n"
        f"🌐 <b>Máy chủ:</b> {server}\n\n"
        "Tài khoản và mật khẩu chỉ giữ trong bộ nhớ khi bot đang chạy."
    )


def _character_text(profile: GameProfile) -> str:
    client = profile.client
    if not client or not client.character.name:
        return (
            "📋 <b>THÔNG TIN NHÂN VẬT</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Chưa có dữ liệu nhân vật. Hãy kết nối máy chủ trước."
        )

    char = client.character
    task = char.task
    task_text = "Chưa nhận dữ liệu nhiệm vụ"
    if task:
        current = task.current_name or task.name
        progress = _num(task.count)
        target = task.target
        if target is not None and target >= 0:
            progress += f" / {_num(target)}"
        detail = task.current_detail or task.detail
        task_text = (
            f"📌 <b>Nhiệm vụ:</b> {_safe(task.name)}\n"
            f"└ {_safe(current)}\n"
            f"📈 <b>Tiến độ:</b> <code>{progress}</code>"
        )
        if detail:
            task_text += f"\n📝 {_safe(detail)}"

    return (
        "📋 <b>THÔNG TIN NHÂN VẬT</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🌐 <b>Máy chủ:</b> {_safe(client.server.name)}\n"
        f"👤 <b>Nhân vật:</b> {_safe(char.name)}\n"
        f"⚡ <b>Sức mạnh:</b> <code>{_num(char.power)}</code>\n"
        f"⏱ <b>Kết nối:</b> <code>{format_duration(client.uptime)}</code>\n\n"
        "💰 <b>TÀI SẢN</b>\n"
        f"🪙 Vàng: <code>{_num(char.gold)}</code>\n"
        f"💎 Ngọc xanh: <code>{_num(char.gem)}</code>\n"
        f"🔴 Ngọc khóa: <code>{_num(char.locked_gem)}</code>\n\n"
        f"{task_text}"
    )


def _character_menu() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [
            [InlineKeyboardButton("🔄 Làm mới", callback_data="boss:character")],
            [InlineKeyboardButton("⬅️ Quay lại", callback_data="boss:menu")],
        ]
    )


def _cancel_input() -> InlineKeyboardMarkup:
    return InlineKeyboardMarkup(
        [[InlineKeyboardButton("Hủy", callback_data="boss:cancel_input")]]
    )


def _server_icon(server: GameServer) -> str:
    if server.language == 0:
        return "🇻🇳"
    if server.language == 1:
        return "🌐"
    if server.language == 2:
        return "🇮🇩"
    return "🛰"


def _server_menu(
    servers: tuple[GameServer, ...],
    selected: GameServer | None,
) -> InlineKeyboardMarkup:
    rows: list[list[InlineKeyboardButton]] = []
    current: list[InlineKeyboardButton] = []
    for server in servers:
        marker = (
            "✅ "
            if selected
            and selected.host == server.host
            and selected.port == server.port
            else ""
        )
        new = "🆕 " if server.is_new else ""
        current.append(
            InlineKeyboardButton(
                f"{marker}{_server_icon(server)} {new}{server.name}",
                callback_data=f"boss:server:{server.id}",
            )
        )
        if len(current) == 2:
            rows.append(current)
            current = []
    if current:
        rows.append(current)
    rows.append([InlineKeyboardButton("🔄 Tải lại", callback_data="boss:servers")])
    rows.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="boss:menu")])
    return InlineKeyboardMarkup(rows)


async def boss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    if not _is_admin(update, context):
        await query.answer("Bạn không có quyền truy cập.", show_alert=True)
        return

    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        await query.answer(
            "Quản lý game chỉ dùng trong chat riêng với bot.",
            show_alert=True,
        )
        return

    manager = _manager(context)
    profile = manager.get(user.id)
    data = query.data if isinstance(query.data, str) else ""

    if data == "boss:menu":
        profile.input_mode = None
        await query.answer()
        await query.edit_message_text(
            _boss_text(profile),
            reply_markup=_menu(profile),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:account":
        profile.input_mode = "account"
        await query.answer()
        await query.edit_message_text(
            "👤 <b>CẤU HÌNH TÀI KHOẢN</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Gửi tên tài khoản game vào khung chat.",
            reply_markup=_cancel_input(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:password":
        profile.input_mode = "password"
        await query.answer()
        await query.edit_message_text(
            "🔑 <b>CẤU HÌNH MẬT KHẨU</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Gửi mật khẩu game vào khung chat.\n\n"
            "Tin nhắn mật khẩu sẽ được bot cố gắng xóa ngay sau khi nhận "
            "và không được ghi log.",
            reply_markup=_cancel_input(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:cancel_input":
        profile.input_mode = None
        await query.answer("Đã hủy")
        await query.edit_message_text(
            _boss_text(profile),
            reply_markup=_menu(profile),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:servers":
        await query.answer("Đang lấy danh sách máy chủ...")
        try:
            servers = await list_servers()
        except Exception as exc:
            await query.edit_message_text(
                "❌ <b>KHÔNG LẤY ĐƯỢC MÁY CHỦ</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"<code>{_safe(exc)}</code>\n\n"
                "Danh sách được lấy trực tiếp từ <code>server_extra.php</code>.",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [InlineKeyboardButton("🔄 Thử lại", callback_data="boss:servers")],
                        [InlineKeyboardButton("⬅️ Quay lại", callback_data="boss:menu")],
                    ]
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        context.application.bot_data["game_servers"] = {
            server.id: server for server in servers
        }
        await query.edit_message_text(
            "🌐 <b>CHỌN MÁY CHỦ</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"Đã tải <b>{len(servers)}</b> máy chủ từ "
            "<code>server_extra.php</code>.\n\n"
            "Chọn máy chủ muốn kết nối:",
            reply_markup=_server_menu(servers, profile.server),
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("boss:server:"):
        try:
            server_id = int(data.rsplit(":", 1)[1])
        except ValueError:
            await query.answer("Máy chủ không hợp lệ", show_alert=True)
            return

        servers = context.application.bot_data.get("game_servers", {})
        server = servers.get(server_id) if isinstance(servers, dict) else None
        if not isinstance(server, GameServer):
            try:
                fresh = await list_servers()
            except Exception as exc:
                await query.answer(
                    f"Không tải lại được máy chủ: {exc}",
                    show_alert=True,
                )
                return
            context.application.bot_data["game_servers"] = {
                item.id: item for item in fresh
            }
            server = next((item for item in fresh if item.id == server_id), None)
        if server is None:
            await query.answer("Không tìm thấy máy chủ", show_alert=True)
            return

        profile.server = server
        await query.answer(f"Đã chọn {server.name}")
        await query.edit_message_text(
            _boss_text(profile),
            reply_markup=_menu(profile),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:connect":
        profile.input_mode = None
        await query.answer("Đang kết nối...")
        await query.edit_message_text(
            "⏳ <b>ĐANG KẾT NỐI GAME</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Đang bắt tay TCP, đăng nhập và lấy dữ liệu nhân vật...",
            parse_mode=ParseMode.HTML,
        )
        try:
            await manager.connect(user.id)
        except Exception as exc:
            await query.edit_message_text(
                "❌ <b>KẾT NỐI THẤT BẠI</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"<code>{_safe(exc)}</code>",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Quay lại", callback_data="boss:menu")]]
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        await query.edit_message_text(
            "✅ <b>KẾT NỐI THÀNH CÔNG</b>\n\n" + _character_text(profile),
            reply_markup=_character_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:disconnect":
        await query.answer("Đang ngắt kết nối...")
        await manager.disconnect(user.id)
        await query.edit_message_text(
            _boss_text(profile),
            reply_markup=_menu(profile),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:character":
        await query.answer()
        await query.edit_message_text(
            _character_text(profile),
            reply_markup=_character_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:check":
        await query.answer(
            "Phần kiểm tra thông báo Boss sẽ làm ở bước tiếp theo.",
            show_alert=True,
        )


async def boss_input(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    message = update.effective_message
    if user is None or message is None or not message.text:
        return
    if not _is_admin(update, context):
        return
    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        return

    profile = _manager(context).get(user.id)
    mode = profile.input_mode
    if mode not in {"account", "password"}:
        return

    value = message.text if mode == "password" else message.text.strip()
    if not value:
        return

    if mode == "account":
        profile.account = value
    else:
        profile.password = value
        try:
            await message.delete()
        except TelegramError:
            pass

    profile.input_mode = None
    await context.bot.send_message(
        chat_id=update.effective_chat.id,
        text=_boss_text(profile),
        reply_markup=_menu(profile),
        parse_mode=ParseMode.HTML,
    )
