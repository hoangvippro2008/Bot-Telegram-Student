# Bot Telegram Student

Bot Telegram viết bằng Python, chạy bằng long polling.

## Cấu trúc

```text
.
├─ bot/
│  ├─ handlers/
│  │  ├─ access.py
│  │  ├─ admin.py
│  │  └─ common.py
│  ├─ app.py
│  ├─ config.py
│  ├─ group.py
│  └─ system.py
├─ main.py
├─ requirements.txt
└─ run.bat
```

## Cài đặt

```bat
python -m pip install -r requirements.txt
```

Tạo `config.json` ở thư mục gốc. File này đã được bỏ khỏi Git để không lộ token.

Ví dụ với nhóm public:

```json
{
  "bot": {
    "token": "BOT_TOKEN",
    "parse_mode": "HTML",
    "admin_ids": [123456789]
  },
  "group": {
    "enabled": true,
    "required_chat": "https://t.me/tennhom",
    "join_url": "https://t.me/tennhom"
  },
  "runtime": {
    "drop_pending_updates": true,
    "allowed_updates": ["message"],
    "log_level": "INFO",
    "bootstrap_retries": 5
  },
  "network": {
    "connect_timeout": 15,
    "read_timeout": 30,
    "error_log_interval": 60
  }
}
```

`required_chat` của nhóm public nhận được cả ba dạng:

```text
https://t.me/tennhom
@tennhom
tennhom
```

Nhóm private không thể dùng link mời để Telegram API kiểm tra thành viên. Dùng chat ID:

```json
"group": {
  "enabled": true,
  "required_chat": -1001234567890,
  "join_url": "https://t.me/+LINK_MOI"
}
```

Muốn lấy ID nhóm private: thêm bot vào nhóm, cấp quyền admin, gửi `/admin` ngay trong nhóm rồi mở **Nhóm người dùng**. Bot sẽ hiện ID chat hiện tại.

Bot nên được cấp quyền quản trị trong nhóm bắt buộc để kiểm tra thành viên ổn định.

## Lệnh

Người dùng:

```text
/start
```

Quản trị viên:

```text
/admin
```

Người chưa tham gia nhóm sẽ bị chặn trước mọi chức năng và nhận nút **Tham gia nhóm** + **Tôi đã tham gia**.

## Chạy

```bat
run.bat
```
