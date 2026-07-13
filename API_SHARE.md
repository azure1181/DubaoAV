# Chia sẻ API dự báo qua LAN và Internet

API chỉ cung cấp dữ liệu đọc (JSON, Excel, PNG và TXT). Không có endpoint ghi hoặc sửa dữ liệu.

## 1. Chạy trong mạng LAN

Chạy:

```bat
run_api_share.cmd
```

Hoặc chạy thủ công:

```powershell
.\.venv\Scripts\python.exe api_website.py --export-json
.\.venv\Scripts\python.exe api_website.py --host 0.0.0.0 --port 8000
```

Khi khởi động, chương trình in ra địa chỉ LAN thực tế, ví dụ:

```text
Chia se LAN: http://192.168.1.25:8000/
```

Máy khác trong cùng mạng truy cập địa chỉ đó. Kiểm tra nhanh:

```text
http://192.168.1.25:8000/healthz
http://192.168.1.25:8000/api
```

Nếu máy khác không kết nối được, cho phép TCP 8000 trên Windows Firewall đối với mạng `Private`. Mở PowerShell bằng quyền Administrator và chỉ chạy một lần:

```powershell
New-NetFirewallRule -DisplayName "Forecast Water API 8000" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8000 -Profile Private
```

Không mở rule cho profile `Public` nếu không thật sự cần.

## 2. Chia sẻ qua Internet

Khuyến nghị đặt API sau reverse proxy hoặc dịch vụ tunnel có HTTPS. Không nên mở thẳng cổng 8000 trên router vì HTTP không mã hóa và toàn bộ báo cáo sẽ công khai.

Chạy API cục bộ cho tunnel/reverse proxy:

```powershell
.\.venv\Scripts\python.exe api_website.py --host 127.0.0.1 --port 8000 --trust-proxy --public-url https://forecast.example.vn --cors-origin https://forecast.example.vn
```

Sau đó cấu hình reverse proxy/tunnel chuyển tiếp URL HTTPS công khai tới:

```text
http://127.0.0.1:8000
```

Thay `https://forecast.example.vn` bằng tên miền thực tế. `--trust-proxy` cho phép API đọc `X-Forwarded-Proto` và `X-Forwarded-Host`; chỉ bật tùy chọn này khi API bind vào `127.0.0.1` hoặc proxy là nguồn truy cập tin cậy.

Nếu URL tunnel thay đổi sau mỗi lần chạy, có thể bỏ `--public-url`; API sẽ dùng các header do proxy gửi.

## 3. Tham số vận hành

```text
--host 0.0.0.0                  Chia sẻ trên LAN
--host 127.0.0.1                Chỉ cho máy cục bộ/reverse proxy
--port 8000                     Cổng lắng nghe
--public-url https://...        URL Internet hiển thị trong /api
--trust-proxy                   Tin header X-Forwarded-* từ proxy
--cors-origin https://...       Origin được phép gọi API
--cors-origin "https://a,https://b"  Cho phép nhiều origin
--quiet                         Tắt access log
--export-json                   Xuất dữ liệu tĩnh cho website
```

Mặc định CORS là `*` để thuận tiện trong LAN. Khi đưa lên Internet, nên giới hạn `--cors-origin` về đúng tên miền website.

## 4. Endpoint chính

```text
GET /healthz
GET /api
GET /api/years
GET /api/forecast?year=2027
GET /api/forecast/all
GET /api/summary?year=2027
GET /api/monthly?year=2027
GET /api/annual?year=2027
GET /api/historical?year=2027
GET /api/calculation?year=2027
GET /api/files?year=2027
GET /chart.png?year=2027
GET /download/2027/bao_cao_du_bao_2027.xlsx
```

API hỗ trợ `GET`, `HEAD` và preflight `OPTIONS`. Dữ liệu Excel được cache trong bộ nhớ và tự nạp lại khi tệp báo cáo thay đổi.

## 5. Xử lý sự cố

- `Address already in use`: đổi cổng bằng `--port 8080` hoặc dừng tiến trình đang dùng cổng 8000.
- Truy cập được trên máy chủ nhưng không được từ máy khác: kiểm tra Windows Firewall và bảo đảm hai máy cùng mạng/VLAN.
- Website mở được nhưng API lỗi qua HTTPS: bật `--trust-proxy` và kiểm tra proxy có gửi `X-Forwarded-Proto: https`.
- `/healthz` hoạt động nhưng năm không có dữ liệu: kiểm tra `/api/years` và các tệp trong `output_forecast`/`Output_2027`.
