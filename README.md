# Bot Telegram Student

Bot Telegram viết bằng Python, chạy bằng long polling.

## Cấu trúc

```text
.
├─ bot/
│  ├─ game/
│  │  ├─ client.py
│  │  ├─ manager.py
│  │  ├─ protocol.py
│  │  └─ server.py
│  ├─ handlers/
│  │  ├─ access.py
│  │  ├─ admin.py
│  │  ├─ admin_boss.py
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

## Kết nối game

Trong `/admin` có mục **Quản lý thông báo Boss**.

Phần hiện tại hỗ trợ:
- nhập tài khoản và mật khẩu trong chat riêng với bot;
- danh sách máy chủ cố định trong `SERVER_LIST`, không fetch `server_extra.php` khi runtime;
- chọn máy chủ và xem trực tiếp `Tên · host:port`;
- kết nối TCP theo giao thức client Teamobi;
- handshake XOR, đăng nhập, đồng bộ Data/Map/Skill/Item và giữ session;
- đọc tên nhân vật, sức mạnh, vàng, ngọc xanh, ngọc khóa và nhiệm vụ hiện tại;
- auto-connect chạy nền, tự thử lại đến khi đăng nhập thành công;
- cập nhật trạng thái auto-connect trực tiếp trên Telegram;
- hủy auto-connect và socket sạch khi bấm **Dừng tự kết nối** hoặc khi bot shutdown.

Mật khẩu chỉ giữ trong RAM khi bot đang chạy. Bot không ghi mật khẩu vào log, source hoặc `config.json`.

## Danh sách máy chủ

Danh sách máy chủ nằm trong `bot/game/server.py`:

```text
SERVER_LIST
```

Vũ trụ 15 hiện được cố định:

```text
Vũ trụ 15 -> dragon15.teamobi.com:14445
```

Mục **Kiểm tra danh sách máy chủ** trong bảng quản trị hiển thị toàn bộ server theo dạng:

```text
Vũ trụ 15
└ dragon15.teamobi.com:14445
```

## Luồng Vũ trụ 15

Vũ trụ 15 dùng luồng tương thích riêng với client Teamobi 2.5.0.

Client gửi:
- `clientType = 4`;
- `zoom = 4`;
- kích thước logic `960x540`;
- `isTouch = true`;
- blob `info` của client 2.5.0.

Luồng chính:

```text
TCP connect
→ handshake -27
→ ClientType
→ ImageSource
→ Login
→ xử lý hàng chờ đăng nhập
→ đồng bộ Data/Map/Skill/Item
→ ClientOk
→ FinishUpdate
→ FinishLoadMap
→ nhận dữ liệu nhân vật
```

### Hàng chờ đăng nhập

Server có thể trả command `122` kèm số giây phải chờ.

Bot xử lý theo state machine:

```text
Login
→ cmd 122
→ giữ nguyên socket
→ đếm ngược đúng số giây server yêu cầu
→ gửi Login lại trên cùng socket
→ nếu lại nhận 122 thì tiếp tục chờ
→ khi nhận -28/4 thì xác nhận đã qua hàng chờ
→ bắt đầu đồng bộ dữ liệu
```

Trong thời gian còn ở hàng chờ:
- không mở thêm socket cho cùng phiên;
- không gửi Data/Map/Skill/Item;
- không gửi `ClientOk`, `FinishUpdate` hoặc `FinishLoadMap`;
- Telegram hiển thị countdown qua trạng thái auto-connect.

Server vẫn là bên quyết định khi nào phiên đăng nhập được chấp nhận. Bot không bypass giới hạn tải hoặc giới hạn số người chơi.

### Packet đăng nhập quan trọng

```text
-27     handshake/key
-26     dialog lỗi hoặc thông báo từ server
122     thời gian chờ đăng nhập
-28/4   server chấp nhận và bắt đầu luồng đồng bộ
-87     Data
-28/6   Map
-28/7   Skill
-28/8   Item
12      hoàn tất Item
-30/0   dữ liệu nhân vật
92      thông báo game/nhiệm vụ
```

Khi nhận `-26`, bot đọc nguyên văn nội dung dialog và báo lỗi ngay thay vì chờ timeout.

## Auto Connect

Bấm **Kết nối máy chủ** một lần để bật auto-connect.

Bot:
1. chỉ chạy một task auto-connect cho mỗi admin;
2. hiển thị số lần thử và trạng thái hiện tại;
3. cập nhật heartbeat khoảng mỗi 3 giây;
4. nếu một phiên TCP thất bại thật sự thì chờ 5 giây rồi thử lại;
5. nếu đang ở hàng chờ `122` của Vũ trụ 15 thì giữ nguyên socket, không tính đó là một lần reconnect;
6. dừng ngay khi nhận được dữ liệu nhân vật;
7. gửi thông báo Telegram khi kết nối thành công.

Ví dụ trạng thái:

```text
AUTO CONNECT ĐANG CHẠY
Máy chủ: Vũ trụ 15
Đích: dragon15.teamobi.com:14445
Lần thử: 1
Trạng thái: Hàng chờ đăng nhập · còn 18s
```

## Log kiểm tra Vũ trụ 15

Các dòng quan trọng:

```text
Game connect: Vũ trụ 15 -> dragon15.teamobi.com:14445
Game handshake: main=... | secondary=... | enabled=...
Game server 15: đã gửi login trên socket hiện tại
Game login queue: chờ N giây trên socket hiện tại
Game server 15: nhận tín hiệu qua hàng chờ (-28/4)
Game sync: clientOk + finishUpdate đã gửi
Game login: finishLoadMap (-39) đã gửi
Game login: nhận nhân vật ...
```

Nếu server trả lỗi:

```text
Game dialog: <nội dung server>
```

## Kiểm tra bản develop

```bat
git switch develop
git pull
run.bat
```

`main` chỉ dùng cho bản ổn định. Các thay đổi mới được kiểm tra trên `develop` trước.

## Thông báo Boss

Mục **Kiểm tra thông báo Boss** hiện mới để sẵn giao diện. Phần parse và gửi thông báo Boss tự động chưa được triển khai ở bản hiện tại.
