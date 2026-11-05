Để chạy và trải nghiệm chức năng **SMS OTP** (gồm Quên mật khẩu & Đăng ký tài khoản), bạn có thể lựa chọn 1 trong 2 cách dưới đây:

---

### CÁCH 1: Chạy kiểm thử tự động (Nhanh nhất - ~0.1 giây)

Script này chạy độc lập kiểm tra toàn bộ 26 trường hợp nghiệp vụ, in mã OTP và tin nhắn mô phỏng ra màn hình mà không cần bật server hay database:

Nếu bạn đang ở thư mục `scripts`:

```powershell
./run_sms_otp_test.py
```

Hoặc nếu đang ở thư mục gốc `E:\parking_management_backend`:

```powershell
uv run python scripts/run_sms_otp_test.py
```

---

### CÁCH 2: Chạy trực tiếp trên Live Server Backend (Swagger / API)

Trong môi trường phát triển (Development), hệ thống sử dụng **`ConsoleSMSBackend`** — nghĩa là khi có yêu cầu gửi SMS, nội dung tin nhắn và **Mã OTP sẽ được in trực tiếp lên màn hình Terminal của server** (không tốn tiền SMS thật).

#### Bước 1: Khởi động máy chủ backend

Mở PowerShell tại thư mục `E:\parking_management_backend`:

```powershell
uv run python manage.py runserver
```

*(Server sẽ khởi động tại `http://127.0.0.1:8000`)*. Giữ nguyên cửa sổ Terminal này để xem tin nhắn SMS in ra.

---

#### Bước 2: Thao tác thực hiện chức năng

Bạn mở trình duyệt vào Swagger UI: **[http://127.0.0.1:8000/api/v1/schema/swagger-ui/](http://127.0.0.1:8000/api/v1/schema/swagger-ui/)** (hoặc dùng Postman / PowerShell):

#### 🔹 LUỒNG 1: Quên mật khẩu qua SMS OTP

1. **Lấy mã OTP**:

   - Gọi API: `POST /api/v1/auth/forgot-password/sms/`
   - Body:
     ```json
     {
       "phone": "0912345678"
     }
     ```
   - Nhìn sang cửa sổ Terminal đang chạy `runserver`, bạn sẽ thấy mã OTP in ra:
     ```text
     ==================== [SMS CONSOLE] ====================
     To:      0912345678
     Message: [Bãi đỗ xe] Mã OTP xác thực đặt lại mật khẩu của bạn là: 482915. Mã có hiệu lực trong 5 phút...
     =======================================================
     ```
2. **Nhập OTP đổi mật khẩu mới**:

   - Gọi API: `POST /api/v1/auth/reset-password/sms/`
   - Body:
     ```json
     {
       "phone": "0912345678",
       "otp": "482915",
       "new_password": "NewSecurePassword123!",
       "confirm_password": "NewSecurePassword123!"
     }
     ```
   - Kết quả: Nhận `HTTP 200` *"Đặt lại mật khẩu thành công. Vui lòng đăng nhập bằng mật khẩu mới."*

---

#### 🔹 LUỒNG 2: Đăng ký tài khoản Khách hàng qua SMS OTP

1. **Gửi yêu cầu OTP đăng ký**:

   - Gọi API: `POST /api/v1/auth/register/sms/request/`
   - Body:
     ```json
     {
       "phone": "0987654321"
     }
     ```
   - Lấy mã OTP 6 số in ra trên Terminal của server.
2. **Xác thực OTP và tạo tài khoản**:

   - Gọi API: `POST /api/v1/auth/register/sms/confirm/`
   - Body:
     ```json
     {
       "phone": "0987654321",
       "otp": "mã_otp_vừa_nhận",
       "password": "CustomerPassword123!",
       "confirm_password": "CustomerPassword123!",
       "full_name": "Nguyễn Văn A",
       "email": "vana@example.com"
     }
     ```
   - Kết quả: Nhận `HTTP 201 Created`, tài khoản khách hàng được tạo với vai trò `CUSTOMER` và hồ sơ khách hàng tự sinh mã `KH%04d`.

---

### Mẹo kiểm tra các tính năng bảo mật:

- **Gửi liên tiếp trong 60 giây**: Hệ thống sẽ chặn và yêu cầu chờ hết thời gian cooldown 60s (`PROP-4.1-P17`).
- **Nhập sai mã OTP 5 lần**: Mã OTP sẽ tự động bị hủy và thông báo yêu cầu gửi mã mới (`PROP-4.1-P16`).
