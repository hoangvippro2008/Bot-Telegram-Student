# Bot Telegram Student

Bot Telegram viết bằng Python, hiện đang chạy bằng long polling.

Project này đang để phần khung chính trước, sau đó mới thêm dần các chức năng cần dùng.

## Cấu trúc

```text
.
├─ bot/
│  ├─ handlers/
│  │  ├─ admin.py
│  │  └─ common.py
│  ├─ app.py
│  ├─ config.py
│  └─ system.py
├─ main.py
├─ requirements.txt
└─ run.bat
```

- `main.py`: điểm chạy chính.
- `bot/app.py`: khởi tạo bot, polling và đăng ký handler.
- `bot/config.py`: đọc và kiểm tra cấu hình.
- `bot/handlers/`: xử lý command, message và admin panel.
- `bot/system.py`: đọc thông tin máy cho admin.

## Cài đặt

Cài thư viện:

```bat
python -m pip install -r requirements.txt
```

Tạo file `config.json` ở thư mục gốc. File này không được push lên Git vì có token bot.

Ví dụ:

```json
{
  "bot": {
    "token": "BOT_TOKEN",
    "parse_mode": "HTML",
    "admin_ids": [123456789]
  },
  "runtime": {
    "drop_pending_updates": true,
    "allowed_updates": ["message"],
    "log_level": "INFO",
    "bootstrap_retries": 5
  },
  "messages": {
    "start": "Bot đang hoạt động. Dùng /help để xem lệnh.",
    "help": "Lệnh hiện có:\n/start - Khởi động bot\n/help - Xem trợ giúp\n/ping - Kiểm tra bot\n/id - Xem Telegram ID",
    "unknown_command": "Lệnh không tồn tại.",
    "text_fallback": "Bot đã nhận tin nhắn.",
    "admin_role": "Role: Admin"
  },
  "network": {
    "connect_timeout": 15,
    "read_timeout": 30,
    "error_log_interval": 60
  }
}
```

`admin_ids` dùng Telegram User ID. Có thể lấy ID bằng lệnh `/id`.

## Chạy bot

```bat
run.bat
```

hoặc:

```bat
python main.py
```

## Lệnh hiện tại

```text
/start
/help
/ping
/id
/admin
```

`/admin` chỉ hoạt động với ID có trong `admin_ids`. Trong Telegram, lệnh này chỉ được đăng ký vào command menu của admin.

Admin panel hiện có:
- Kiểm tra thông tin
- Thông tin hệ thống
- Trạng thái bot

Phần kiểm tra hệ thống hiển thị CPU, logical cores, threads, RAM, RAM của process bot, ổ đĩa, hệ điều hành, Python, PID và uptime.
