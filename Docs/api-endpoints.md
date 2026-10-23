# Danh mục API hiện có

Tài liệu này mô tả các route đang được khai báo trong `config/urls.py` và các URL configuration của ứng dụng. Đây là ảnh chụp trạng thái mã nguồn hiện tại, không phải danh sách chức năng dự kiến theo SRS.

> **Phạm vi hiện tại:** trong các API nghiệp vụ, chỉ endpoint đăng nhập được nối vào URL routing. Các app khách hàng, nhân viên, phương tiện, vé, bãi đỗ và báo cáo đã được include ở cấp dự án nhưng `urlpatterns` của chúng hiện chưa khai báo endpoint nào.

## Quy ước chung

- API nghiệp vụ dùng tiền tố `/api/v1/`.
- Payload và response của endpoint đăng nhập dùng JSON.
- Đăng nhập sử dụng Django session; request đăng nhập thành công thiết lập session cookie. `remember_me` hiện tạo bản ghi token phía server nhưng mã hiện tại không trả token cho client và cũng không đặt remember-me cookie.
- `LoginView` cho phép truy cập chưa đăng nhập (`AllowAny`). Cấu hình REST Framework mặc định dùng `SessionAuthentication` và yêu cầu xác thực cho các API khác, nếu các API đó được triển khai.
- Giá trị `BASE_URL` phụ thuộc môi trường. Ví dụ bên dưới dùng `http://localhost:8000` khi chạy local.

## API nghiệp vụ đã triển khai

### Đăng nhập

| Thuộc tính | Giá trị                                                                                                                  |
| ------------ | -------------------------------------------------------------------------------------------------------------------------- |
| Method       | `POST`                                                                                                                   |
| URL          | `/api/v1/login/`                                                                                                         |
| Xác thực   | Không yêu cầu đăng nhập trước (`AllowAny`)                                                                       |
| Content-Type | `application/json`                                                                                                       |
| CSRF         | View được gắn `ensure_csrf_cookie`; với client dùng session/CSRF, lấy và gửi CSRF token theo cấu hình Django. |

**Request body**

| Trường        | Kiểu   | Bắt buộc | Mô tả                                                                                                                                             |
| --------------- | ------- | ---------: | --------------------------------------------------------------------------------------------------------------------------------------------------- |
| `username`    | string  |        Có | Tên đăng nhập; được trim khoảng trắng ở đầu và cuối. Chỉ chấp nhận chữ cái ASCII, chữ số, `_`, `.`, `-`.                 |
| `password`    | string  |        Có | Mật khẩu.                                                                                                                                         |
| `remember_me` | boolean |     Không | Mặc định `false`. Khi `true`, tạo persistent-login-token record có hạn dùng 30 ngày. Token bí mật không được trả trong response. |

**Ví dụ request**

```http
POST /api/v1/login/ HTTP/1.1
Content-Type: application/json

{
  "username": "employee01",
  "password": "ExamplePassword123!",
  "remember_me": false
}
```

**Response thành công — `200 OK`**

```json
{
  "success": true,
  "data": {
    "user": {
      "id": 12,
      "username": "employee01",
      "role": "EMPLOYEE",
      "is_staff": false,
      "is_superuser": false
    }
  }
}
```

Django session được thiết lập ở response; client cần lưu/gửi cookie session cho các request được xác thực tiếp theo.

**Các lỗi được xử lý trong view**

|    HTTP | `error.code`          | Điều kiện                                 | `error.message`                                               |
| ------: | ----------------------- | -------------------------------------------- | --------------------------------------------------------------- |
| `400` | `VALIDATION_ERROR`    | Thiếu username hoặc password               | `Xin nhập đầy đủ Tên đăng nhập và Mật khẩu`       |
| `400` | `VALIDATION_ERROR`    | Username chứa ký tự ngoài tập cho phép | `Tên đăng nhập không chứa ký tự đặc biệt`          |
| `401` | `INVALID_CREDENTIALS` | Sai username hoặc password                  | `Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu` |
| `403` | `ACCOUNT_DISABLED`    | Tài khoản không hoạt động              | `Tài khoản đã được vô hiệu hóa`                     |
| `500` | `SERVER_ERROR`        | Lỗi không xử lý khác trong view         | `Lỗi hệ thống`                                             |

Các lỗi trên có cấu trúc chung:

```json
{
  "success": false,
  "error": {
    "code": "VALIDATION_ERROR",
    "message": "Thông báo lỗi",
    "details": [
      {
        "field": "username",
        "message": "Thông báo lỗi"
      }
    ]
  }
}
```

`field` là trường liên quan (`username`, `password`) hoặc `non_field` cho lỗi không gắn với một trường cụ thể. Với JSON sai cú pháp hoặc lỗi phân tích request, DRF có thể trả lỗi ở tầng parser trước khi xử lý logic trong view; response đó không nhất thiết dùng envelope trên.

## Route tài liệu API

| Method  | URL              | Mô tả                                       |
| ------- | ---------------- | --------------------------------------------- |
| `GET` | `/api/schema/` | Sinh OpenAPI schema qua drf-spectacular.      |
| `GET` | `/api/docs/`   | Swagger UI, tải schema từ `/api/schema/`. |
| `GET` | `/api/redoc/`  | ReDoc, tải schema từ `/api/schema/`.      |

Đây là route tài liệu/schema, không phải endpoint nghiệp vụ. Nội dung schema chỉ phản ánh những route và metadata mà ứng dụng hiện khai báo.

## Chạy server và mở Swagger UI

### 1. Chuẩn bị môi trường local

Tại thư mục gốc của repository, tạo/cấu hình file `.env` theo `.env.example` và điền thông tin database local. Không đưa mật khẩu hoặc secret thật vào tài liệu hay commit.

Khởi động PostgreSQL bằng Docker Compose:

```bash
docker compose up -d db
```

Cài dependencies nếu môi trường Python chưa được cài đặt:

```bash
python -m venv .venv
```

Windows PowerShell:

```powershell
.venv\Scripts\Activate.ps1
pip install -r requirements/dev.txt
```

macOS/Linux:

```bash
source .venv/bin/activate
pip install -r requirements/dev.txt
```

Chạy migration rồi khởi động Django development server:

```bash
python manage.py migrate
python manage.py runserver
```

### 2. Mở giao diện API từ manage.py runserver

Khi server chạy local tại cổng mặc định, mở:

- Swagger UI: [http://127.0.0.1:8000/api/docs/](http://127.0.0.1:8000/api/docs/)
- OpenAPI schema dạng JSON: [http://127.0.0.1:8000/api/schema/](http://127.0.0.1:8000/api/schema/)
- ReDoc: [http://127.0.0.1:8000/api/redoc/](http://127.0.0.1:8000/api/redoc/)

Nếu chạy server trên host/cổng khác, thay `127.0.0.1:8000` bằng host/cổng đó. Nếu không mở được trang, kiểm tra server còn chạy, cấu hình database trong `.env`, và log của lệnh `runserver`.

### 3. Khám phá và gọi API bằng Swagger UI

1. Mở `/api/docs/`; Swagger UI đọc định nghĩa từ `/api/schema/`.
2. Mở nhóm `accounts` và chọn `POST /api/v1/login/`.
3. Chọn **Try it out**, nhập JSON body theo ví dụ đăng nhập ở phần trên. Dùng tài khoản đã tồn tại trong database local; không ghi mật khẩu thật vào tài liệu hoặc chia sẻ ảnh chụp màn hình có thông tin đăng nhập.
4. Chọn **Execute** để gửi request.
5. Xem `Server response` để đọc status code và response body. Thành công trả `200` cùng thông tin user và session cookie; lỗi trả status/message tương ứng trong bảng lỗi.

Hiện Swagger chỉ có thể hiển thị endpoint nghiệp vụ đã được khai báo thực tế. Các module khách hàng, nhân viên, phương tiện, vé, bãi đỗ và báo cáo chưa có route, nên chúng sẽ không xuất hiện như API có thể gọi trong Swagger.


### 4. Gọi endpoint đăng nhập ngoài Swagger cho hệ thống

Ví dụ dùng `curl` từ terminal; thay placeholder bằng tài khoản local hợp lệ. Tùy shell, có thể cần gọi `curl.exe` trên Windows PowerShell.

```bash
curl -i -X POST "http://127.0.0.1:8000/api/v1/login/" -H "Content-Type: application/json" -c cookies.txt -d '{"username":"<username>","password":"<password>","remember_me":false}'
```

`-i` hiển thị status và response headers; `-c cookies.txt` lưu cookie session do Django trả về. Không chia sẻ hoặc commit file cookie. Client muốn giữ trạng thái đăng nhập cần bảo quản cookie này an toàn và gửi lại ở các request tiếp theo. Hiện chưa có endpoint nghiệp vụ được nối để minh họa request đã xác thực.

### 5. Lấy OpenAPI schema

Xem schema trên trình duyệt tại `/api/schema/`, hoặc tải xuống từ terminal:

```bash
curl "http://127.0.0.1:8000/api/schema/" -o openapi-schema.yml
```

Schema được tạo từ URL và metadata đang có trong ứng dụng; tải schema không tự tạo thêm API. Sau khi endpoint mới được triển khai và khai báo đầy đủ, chạy lại lệnh trên để lấy bản cập nhật.

## Route ngoài API nghiệp vụ

| Method        | URL         | Mô tả                                            |
| ------------- | ----------- | -------------------------------------------------- |
| Nhiều method | `/admin/` | Django Admin; không thuộc REST API `/api/v1/`. |

## Các module chưa có endpoint được nối

Các URL configuration dưới đây hiện để trống hoặc chỉ có comment giữ chỗ; không nên coi đây là API đã triển khai:

| Module                 | URL configuration          |
| ---------------------- | -------------------------- |
| Khách hàng           | `apps/customers/urls.py` |
| Nhân viên            | `apps/employees/urls.py` |
| Phương tiện vào/ra | `apps/vehicles/urls.py`  |
| Vé                    | `apps/tickets/urls.py`   |
| Bãi đỗ/vị trí     | `apps/parking/urls.py`   |
| Báo cáo/thống kê   | `apps/reports/urls.py`   |

Các path liên quan trong danh mục yêu cầu/SRS chỉ được thêm vào tài liệu endpoint đã triển khai sau khi có URL route và view thực tế.

## Nguồn đối chiếu trong mã nguồn

- `config/urls.py` — include URL của các app và các route schema/Swagger/ReDoc.
- `apps/accounts/urls.py` — route `/login/`.
- `apps/accounts/login_views.py` — xử lý đăng nhập, validation và response.
- `config/settings/base.py` — cấu hình DRF, authentication và drf-spectacular.
