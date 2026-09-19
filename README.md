# Bot Telegram Student

Bot Telegram viết bằng Python, hiện đang chạy bằng long polling.

Project này đang để phần khung chính trước, sau đó mới thêm dần các chức năng cần dùng.

## Cấu trúc

```text
.
├─ bot/
│  ├─ handlers/
│  │  └─ common.py
│  ├─ app.py
│  └─ config.py
├─ main.py
├─ requirements.txt
└─ run.bat
```

- `main.py`: điểm chạy chính.
- `bot/app.py`: khởi tạo bot, polling và đăng ký handler.
- `bot/config.py`: đọc và kiểm tra cấu hình.
- `bot/handlers/`: xử lý command và message.

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

## Chạy bot

Có thể chạy trực tiếp:

```bat
python main.py
```

hoặc:

```bat
run.bat
```

## Lệnh hiện tại

```text
/start
/help
/ping
/id
```

Các chức năng khác sẽ được thêm trực tiếp vào project khi cần.
