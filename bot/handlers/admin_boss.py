from __future__ import annotations

import hashlib
import html

from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update
from telegram.constants import ChatType, ParseMode
from telegram.error import BadRequest, TelegramError
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


def _server_token(server: GameServer) -> str:
    raw = f"{server.name}\0{server.host}\0{server.port}".encode("utf-8")
    return hashlib.blake2s(raw, digest_size=8).hexdigest()


async def _answer(query, text: str | None = None, show_alert: bool = False) -> bool:
    try:
        await query.answer(text=text, show_alert=show_alert)
        return True
    except BadRequest as exc:
        message = str(exc).lower()
        if (
            "query is too old" in message
            or "response timeout expired" in message
            or "query id is invalid" in message
        ):
            return False
        raise


async def _edit(
    query,
    text: str,
    reply_markup: InlineKeyboardMarkup | None = None,
    parse_mode: str | None = ParseMode.HTML,
) -> bool:
    try:
        await query.edit_message_text(
            text=text,
            reply_markup=reply_markup,
            parse_mode=parse_mode,
        )
        return True
    except BadRequest as exc:
        if "message is not modified" in str(exc).lower():
            return False
        raise


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
            [InlineKeyboardButton("📡 Kiểm tra danh sách máy chủ", callback_data="boss:server_list:0")],
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
    endpoint = (
        f"<code>{_safe(profile.server.host)}:{profile.server.port}</code>"
        if profile.server
        else "Chưa chọn"
    )

    return (
        "🔔 <b>QUẢN LÝ THÔNG BÁO BOSS</b>\n"
        "━━━━━━━━━━━━━━━━━━\n"
        f"🔌 <b>Trạng thái:</b> {status}\n"
        f"👤 <b>Tài khoản:</b> <code>{account}</code>\n"
        f"🔑 <b>Mật khẩu:</b> {password}\n"
        f"🌐 <b>Máy chủ:</b> {server}\n"
        f"📡 <b>Đích:</b> {endpoint}\n\n"
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
    task_text = (
        f"📌 <b>Nhiệm vụ:</b> {_safe(char.mission_notice)}"
        if char.mission_notice
        else "Chưa nhận dữ liệu nhiệm vụ"
    )
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
    for server in servers:
        marker = (
            "✅ "
            if selected
            and selected.host == server.host
            and selected.port == server.port
            else ""
        )
        new = "🆕 " if server.is_new else ""
        rows.append(
            [
                InlineKeyboardButton(
                    f"{marker}{_server_icon(server)} {new}{server.name} · "
                    f"{server.host}:{server.port}",
                    callback_data=f"boss:server:{_server_token(server)}",
                )
            ]
        )

    rows.append(
        [
            InlineKeyboardButton(
                "📡 Kiểm tra danh sách máy chủ",
                callback_data="boss:server_list:0",
            )
        ]
    )
    rows.append([InlineKeyboardButton("🔄 Tải lại", callback_data="boss:servers")])
    rows.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="boss:menu")])
    return InlineKeyboardMarkup(rows)


_SERVER_PAGE_SIZE = 12


def _server_list_text(
    servers: tuple[GameServer, ...],
    selected: GameServer | None,
    page: int,
) -> str:
    total_pages = max(1, (len(servers) + _SERVER_PAGE_SIZE - 1) // _SERVER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    start = page * _SERVER_PAGE_SIZE
    end = min(start + _SERVER_PAGE_SIZE, len(servers))

    lines = [
        "📡 <b>DANH SÁCH MÁY CHỦ</b>",
        "━━━━━━━━━━━━━━━━━━",
        f"Trang <b>{page + 1}/{total_pages}</b> · Tổng <b>{len(servers)}</b> máy chủ",
        "",
    ]

    for server in servers[start:end]:
        selected_mark = (
            "✅"
            if selected
            and selected.host == server.host
            and selected.port == server.port
            else "▫️"
        )
        new = " 🆕" if server.is_new else ""
        lines.append(
            f"{selected_mark} <b>{_safe(server.name)}</b>{new}\n"
            f"└ <code>{_safe(server.host)}:{server.port}</code>"
        )

    lines.extend(
        [
            "",
            "Nguồn: <code>server_extra.php</code>",
            "✅ là máy chủ đang được chọn để kết nối.",
        ]
    )
    return "\n".join(lines)


def _server_list_menu(page: int, total: int) -> InlineKeyboardMarkup:
    total_pages = max(1, (total + _SERVER_PAGE_SIZE - 1) // _SERVER_PAGE_SIZE)
    page = max(0, min(page, total_pages - 1))
    nav: list[InlineKeyboardButton] = []

    if page > 0:
        nav.append(
            InlineKeyboardButton(
                "⬅️ Trang trước",
                callback_data=f"boss:server_list:{page - 1}",
            )
        )
    if page + 1 < total_pages:
        nav.append(
            InlineKeyboardButton(
                "Trang sau ➡️",
                callback_data=f"boss:server_list:{page + 1}",
            )
        )

    rows: list[list[InlineKeyboardButton]] = []
    if nav:
        rows.append(nav)
    rows.append(
        [InlineKeyboardButton("🔄 Làm mới", callback_data=f"boss:server_list:{page}")]
    )
    rows.append([InlineKeyboardButton("🌐 Chọn máy chủ", callback_data="boss:servers")])
    rows.append([InlineKeyboardButton("⬅️ Quay lại", callback_data="boss:menu")])
    return InlineKeyboardMarkup(rows)


async def boss_callback(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    query = update.callback_query
    user = update.effective_user
    if query is None or user is None:
        return
    if not _is_admin(update, context):
        await _answer(query, "Bạn không có quyền truy cập.", show_alert=True)
        return

    if not update.effective_chat or update.effective_chat.type != ChatType.PRIVATE:
        await _answer(
            query,
            "Quản lý game chỉ dùng trong chat riêng với bot.",
            show_alert=True,
        )
        return

    manager = _manager(context)
    profile = manager.get(user.id)
    data = query.data if isinstance(query.data, str) else ""

    if data == "boss:menu":
        profile.input_mode = None
        await _answer(query)
        await _edit(query, 
            _boss_text(profile),
            reply_markup=_menu(profile),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:account":
        profile.input_mode = "account"
        await _answer(query)
        await _edit(query, 
            "👤 <b>CẤU HÌNH TÀI KHOẢN</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Gửi tên tài khoản game vào khung chat.",
            reply_markup=_cancel_input(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:password":
        profile.input_mode = "password"
        await _answer(query)
        await _edit(query, 
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
        await _answer(query, "Đã hủy")
        await _edit(query, 
            _boss_text(profile),
            reply_markup=_menu(profile),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:servers":
        await _answer(query, "Đang lấy danh sách máy chủ...")
        try:
            servers = await list_servers()
        except Exception as exc:
            await _edit(
                query,
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

        profile.server_options = {
            _server_token(server): server for server in servers
        }

        selected_text = "Chưa chọn"
        if profile.server:
            selected_text = (
                f"{_safe(profile.server.name)} · "
                f"<code>{_safe(profile.server.host)}:{profile.server.port}</code>"
            )

        await _edit(
            query,
            "🌐 <b>CHỌN MÁY CHỦ</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            f"Đã tải <b>{len(servers)}</b> máy chủ trực tiếp từ "
            "<code>server_extra.php</code>.\n"
            f"🎯 <b>Đang chọn:</b> {selected_text}\n\n"
            "Mỗi nút bên dưới hiển thị đúng <b>Tên · host:port</b>:",
            reply_markup=_server_menu(servers, profile.server),
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("boss:server_list:"):
        await _answer(query, "Đang kiểm tra danh sách...")
        try:
            page = int(data.rsplit(":", 1)[1])
        except ValueError:
            page = 0

        try:
            servers = await list_servers()
        except Exception as exc:
            await _edit(
                query,
                "❌ <b>KHÔNG KIỂM TRA ĐƯỢC MÁY CHỦ</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"<code>{_safe(exc)}</code>",
                reply_markup=InlineKeyboardMarkup(
                    [
                        [
                            InlineKeyboardButton(
                                "🔄 Thử lại",
                                callback_data="boss:server_list:0",
                            )
                        ],
                        [InlineKeyboardButton("⬅️ Quay lại", callback_data="boss:menu")],
                    ]
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        profile.server_options = {
            _server_token(server): server for server in servers
        }
        total_pages = max(
            1,
            (len(servers) + _SERVER_PAGE_SIZE - 1) // _SERVER_PAGE_SIZE,
        )
        page = max(0, min(page, total_pages - 1))

        await _edit(
            query,
            _server_list_text(servers, profile.server, page),
            reply_markup=_server_list_menu(page, len(servers)),
            parse_mode=ParseMode.HTML,
        )
        return

    if data.startswith("boss:server:"):
        token = data.rsplit(":", 1)[1]
        server = profile.server_options.get(token)

        if not isinstance(server, GameServer):
            try:
                fresh = await list_servers()
            except Exception as exc:
                await _answer(
                    query,
                    f"Không tải lại được máy chủ: {exc}",
                    show_alert=True,
                )
                return

            profile.server_options = {
                _server_token(item): item for item in fresh
            }
            server = profile.server_options.get(token)

        if not isinstance(server, GameServer):
            await _answer(
                query,
                "Danh sách máy chủ đã thay đổi. Hãy mở Chọn máy chủ và chọn lại.",
                show_alert=True,
            )
            return

        profile.server = server
        await _answer(
            query,
            f"Đã chọn {server.name} ({server.host}:{server.port})",
        )
        await _edit(query, 
            _boss_text(profile),
            reply_markup=_menu(profile),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:connect":
        profile.input_mode = None
        await _answer(query, "Đang kết nối...")
        await _edit(query, 
            "⏳ <b>ĐANG KẾT NỐI GAME</b>\n"
            "━━━━━━━━━━━━━━━━━━\n"
            "Đang bắt tay TCP, đăng nhập và lấy dữ liệu nhân vật...",
            parse_mode=ParseMode.HTML,
        )
        try:
            await manager.connect(user.id)
        except Exception as exc:
            await _edit(query, 
                "❌ <b>KẾT NỐI THẤT BẠI</b>\n"
                "━━━━━━━━━━━━━━━━━━\n"
                f"<code>{_safe(exc)}</code>",
                reply_markup=InlineKeyboardMarkup(
                    [[InlineKeyboardButton("⬅️ Quay lại", callback_data="boss:menu")]]
                ),
                parse_mode=ParseMode.HTML,
            )
            return

        await _edit(query, 
            "✅ <b>KẾT NỐI THÀNH CÔNG</b>\n\n" + _character_text(profile),
            reply_markup=_character_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:disconnect":
        await _answer(query, "Đang ngắt kết nối...")
        await manager.disconnect(user.id)
        await _edit(query, 
            _boss_text(profile),
            reply_markup=_menu(profile),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:character":
        await _answer(query)
        await _edit(query, 
            _character_text(profile),
            reply_markup=_character_menu(),
            parse_mode=ParseMode.HTML,
        )
        return

    if data == "boss:check":
        await _answer(
            query,
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
