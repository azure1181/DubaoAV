# Triển khai Forecast Water API lên Render

[![Deploy to Render](https://render.com/images/deploy-to-render-button.svg)](https://render.com/deploy?repo=https://github.com/azure1181/DubaoAV)

## Kiến trúc

Render chạy `api_website.py` như một Python Web Service. Website, JSON API và các tệp tải xuống dùng chung một URL `https://<ten-dich-vu>.onrender.com`.

Các tệp triển khai đã có sẵn:

- `render.yaml`: Blueprint của Render.
- `requirements.txt`: thư viện Python cần cho API.
- `.python-version`: dòng Python 3.14.
- `/healthz`: endpoint health check.

## 1. Đưa mã nguồn lên GitHub

Tạo một repository **Private** trên GitHub. Không commit `.venv`, `__pycache__`, token hoặc tệp `.env`.

Repository phải chứa tối thiểu:

```text
api_website.py
render.yaml
requirements.txt
.python-version
web_report/
output_forecast/
Output_2027/
```

Hai thư mục kết quả phải chứa các tệp Excel, PNG và TXT mà API đang phục vụ.

## 2. Tạo Blueprint trên Render

1. Đăng nhập Render và kết nối tài khoản GitHub.
2. Chọn **New > Blueprint**.
3. Chọn repository vừa tạo.
4. Render đọc `render.yaml` và tạo service `forecast-water-api`.
5. Chọn **Apply** và chờ build hoàn tất.

Render tự cấp URL dạng:

```text
https://forecast-water-api.onrender.com
```

Kiểm tra:

```text
https://forecast-water-api.onrender.com/healthz
https://forecast-water-api.onrender.com/
https://forecast-water-api.onrender.com/api
https://forecast-water-api.onrender.com/api/forecast?year=2027
```

## 3. Giới hạn CORS

Sau lần deploy đầu tiên, vào **Service > Environment** và đổi:

```text
CORS_ORIGIN=https://forecast-water-api.onrender.com
PUBLIC_URL=https://forecast-water-api.onrender.com
```

Nếu gắn tên miền riêng, thay hai giá trị trên bằng tên miền riêng, ví dụ `https://forecast.example.vn`.

## 4. Cập nhật báo cáo

Render tự deploy lại sau mỗi commit lên nhánh đã kết nối. Quy trình cập nhật:

1. Chạy dự báo ở máy cục bộ.
2. Kiểm tra các tệp mới trong `output_forecast/` hoặc `Output_2027/`.
3. Commit và push các tệp kết quả lên GitHub.
4. Render tự build và phát hành phiên bản mới.

Không chạy `forecast_water_2026.py` hoặc `forecast_water_2027.py` trong bước build cloud, vì hai script này phụ thuộc workbook nguồn cục bộ. Cloud chỉ phục vụ các báo cáo đã tạo.

## 5. Lưu ý vận hành

- Filesystem của web service không phải nơi lưu dữ liệu cập nhật lâu dài. Các báo cáo cần được commit vào Git hoặc chuyển sang object storage nếu muốn cập nhật qua API.
- API hiện là dịch vụ đọc công khai. Ai có URL đều có thể đọc và tải báo cáo.
- Không đưa workbook vận hành gốc hoặc dữ liệu nhạy cảm lên repository nếu không cần thiết.
- Nếu dùng gói có chế độ ngủ khi không hoạt động, request đầu tiên sau thời gian nghỉ có thể chậm hơn.
