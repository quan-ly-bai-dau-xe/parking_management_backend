"""
Centralized Message Catalog for Parking Management Backend.
Contains verbatim dialogue messages from SRS v4.1 (MSG-*)
and approved proposal messages (PROP-*).
"""

# Verbatim messages extracted directly from Quan ly bai dau xe oto_SRS_v4.1.docx
SRS_MESSAGES = {
    "MSG-4.1-M01": "MSG-<Screen>-M<Sequence>",
    "MSG-4.1-M02": "Xin vui lòng nhập lại Tên đăng nhập hoặc Mật khẩu",
    "MSG-4.1-M03": "Xin nhập đầy đủ Tên đăng nhập và Mật khẩu",
    "MSG-4.2-M01": "Thông báo lỗi hệ thống",
    "MSG-4.2-M02": "Thông báo lỗi hệ thống, hoặc lỗi kết nối mạng",
    "MSG-4.3.1-M01": "Xóa thành công",
    "MSG-4.3.1-M02": "Xóa thành công",
    "MSG-4.3.1-M03": "Dữ liệu hiện đang được cập nhật bởi user khác",
    "MSG-4.3.1-M04": "Dữ liệu hiện đang được cập nhật bởi user khác",
    "MSG-4.3.1-M05": "Không có dữ liệu trùng",
    "MSG-4.3.1-M06": "Không có dữ liệu trùng",
    "MSG-4.3.1-M07": "Không có dữ liệu được tìm thấy",
    "MSG-4.3.2-M01": "Đã thêm thành công nhân viên",
    "MSG-4.3.2-M02": "MSG-<Screen>-M<Sequence>",
    "MSG-4.3.2-M03": "Đã thêm thành công nhân viên",
    "MSG-4.3.3-M01": "Dữ liệu {item} không đúng định dạng, ..",
    "MSG-4.3.3-M02": "Thông báo lỗi Server",
    "MSG-4.3.4-M01": "Xóa thành công",
    "MSG-4.3.4-M02": "Xóa thành công",
    "MSG-4.3.4-M03": "Xóa thành công",
    "MSG-4.4.1-M01": "Không tìm thấy dữ liệu",
    "MSG-4.4.1-M02": "Không tìm thấy dữ liệu",
    "MSG-4.4.1-M03": "Lỗi kết nối",
    "MSG-4.4.2-M01": "Lỗi kết nối",
    "MSG-4.4.3-M01": "Lỗi hệ thống",
    "MSG-4.4.3-M02": "Dữ liệu trên trường {item} không đúng định dạng …",
    "MSG-4.4.3-M03": "Dữ liệu trên trường {item} không đúng định dạng …",
    "MSG-4.4.3-M04": "Lỗi kết nối",
    "MSG-4.4.3-M05": "Lỗi kế nối",
    "MSG-4.4.4-M01": "Dữ liệu trên trường {item} không đúng định dạng …",
    "MSG-4.4.4-M02": "Dữ liệu trên trường {item} không đúng định dạng …",
    "MSG-4.4.4-M03": "Lỗi hệ thống",
    "MSG-4.4.4-M04": "Lỗi kế nối",
    "MSG-4.4.5-M01": "Xóa thành công",
    "MSG-4.4.5-M02": "Xóa thành công",
    "MSG-4.4.5-M03": "Xóa thành công",
    "MSG-4.5.1-M01": "Không tìm thấy dữ liệu trùng khớp",
    "MSG-4.5.1-M02": "Lỗi dữ liệu không tìm thấy đê lưu",
    "MSG-4.5.1-M03": "Lỗi dữ liệu không tìm thấy đê lưu",
    "MSG-4.5.2-M01": "Lỗi kết nối",
    "MSG-4.5.2-M02": "Vị trí này đã có xe đk vé và đang sử dụng",
    "MSG-4.5.2-M03": "Vị trí này đã có xe đk vé và đang sử dụng",
    "MSG-4.6.1-M01": "Không tìm thấy dữ liệu",
    "MSG-4.6.1-M02": "Không tìm thấy dữ liệu",
    "MSG-4.6.1-M03": "Lỗi kết nối",
    "MSG-4.6.2-M01": "Dữ liệu {item} không hợp lệ",
    "MSG-4.6.2-M02": "Dữ liệu {item} không hợp lệ",
    "MSG-4.6.2-M03": "Lỗi kết nối",
    "MSG-4.6.3-M01": "Lỗi dữ liệu trên {item} không hợp lệ",
    "MSG-4.6.3-M02": "Lỗi dữ liệu trên {item} không hợp lệ",
    "MSG-4.6.3-M03": "Lỗi kết nối",
    "MSG-4.6.4-M01": "Xóa thành công",
    "MSG-4.7.1-M01": "Dữ liệu không tìm thấy",
    "MSG-4.8.4-M01": "Có vấn đề, Không thể quay lại trang danh sách vị trí",
    "MSG-4.8.5-M04": "Lỗi kết nối",
}

# Approved Proposal Messages ([PROPOSAL]) per docs/requirements/05-proposed-messages.md
PROPOSAL_MESSAGES = {
    "PROP-4.3.1-P01": "Dữ liệu {item} không hợp lệ, xin mời nhập lại.",
    "PROP-4.3.3-P01": "Cập nhật thông tin nhân viên thành công.",
    "PROP-4.3.3-P02": "Nhân viên không tồn tại hoặc đã bị xóa.",
    "PROP-4.4.3-P01": "Thêm mới thông tin khách hàng thành công.",
    "PROP-4.4.4-P01": "Cập nhật thông tin khách hàng thành công.",
    "PROP-4.4.4-P02": "Khách hàng không tồn tại hoặc đã bị xóa.",
    "PROP-4.4.5-P01": "Khách hàng không tồn tại hoặc đã bị xóa.",
    "PROP-4.4.5-P02": "Khách hàng đang có phương tiện trong bãi, không được phép xóa.",
    "PROP-4.4.5-P03": "Khách hàng đang có vé xe còn hiệu lực, không được phép xóa.",
    "PROP-4.5.2-P01": "Vị trí này đang bảo trì.",
    "PROP-4.5.2-P02": "Không thể chuyển trạng thái vị trí khi đang có xe đỗ trong ô.",
    "PROP-4.5.2-P03": "Không thể chuyển vị trí sang trạng thái đang có xe khi không có phiên đỗ xe đang mở.",
    "PROP-4.5.2-P04": "Không thể đánh dấu vị trí trống khi đang có xe đỗ hoặc đặt trước còn hiệu lực.",
    "PROP-4.5.2-P05": "Vị trí này đã được đặt trước cho phương tiện khác.",
    "PROP-4.5.2-P06": "Nhật ký hoạt động là bảng chỉ ghi (append-only), không cho phép cập nhật hoặc xóa.",
    "PROP-4.6.2-P01": "Thêm mới vé đỗ xe thành công.",
    "PROP-4.6.3-P01": "Gia hạn vé đỗ xe thành công.",
    "PROP-4.6.4-P01": "Vé chưa hết hạn, không được phép xóa.",
    "PROP-4.6.4-P02": "Vé đã được gia hạn, không được phép xóa.",
    "PROP-4.6.4-P03": "Vé đang được xử lý bởi người dùng khác, vui lòng thử lại sau.",
    "PROP-4.6.4-P04": "Lỗi kết nối cơ sở dữ liệu khi thực hiện xóa vé.",
    "PROP-4.6.4-P05": "Vé không tồn tại hoặc đã bị xóa.",
    "PROP-4.7.1-P01": "Dữ liệu điều kiện thống kê không hợp lệ.",
    "PROP-4.7.1-P02": "Lỗi kết nối hệ thống khi tạo biểu đồ thống kê.",
    "PROP-4.7.2-P01": "Không có dữ liệu phù hợp để thống kê.",
    "PROP-4.7.2-P02": "Khoảng thời gian thống kê không hợp lệ (Từ ngày phải nhỏ hơn hoặc bằng Đến ngày).",
    "PROP-4.7.2-P03": "Lỗi kết nối hệ thống khi thực hiện thống kê.",
    "PROP-4.8.2-P01": "Thêm mới vị trí đỗ xe thành công.",
    "PROP-4.8.2-P02": "Dữ liệu vị trí đỗ xe không hợp lệ, xin mời nhập lại.",
    "PROP-4.8.2-P03": "Vị trí đỗ xe đã tồn tại trên tầng này.",
    "PROP-4.8.2-P04": "Lỗi kết nối máy chủ khi thêm vị trí đỗ xe.",
    "PROP-4.8.3-P01": "Cập nhật thông tin vị trí đỗ xe thành công.",
    "PROP-4.8.3-P02": "Dữ liệu cập nhật vị trí đỗ xe không hợp lệ.",
    "PROP-4.8.3-P03": "Vị trí đỗ xe đang được cập nhật bởi người dùng khác.",
    "PROP-4.8.3-P04": "Lỗi kết nối máy chủ khi cập nhật vị trí đỗ xe.",
    "PROP-4.8.5-P01": "Xóa vị trí đỗ xe thành công.",
    "PROP-4.8.5-P02": "Vị trí đỗ xe đang có phương tiện đăng ký vé, không được phép xóa.",
    "PROP-4.8.5-P03": "Vị trí đỗ xe đang được xóa bởi người dùng khác.",
    "PROP-4.8.5-P04": "Lỗi kết nối máy chủ khi xóa vị trí đỗ xe.",
    "PROP-4.8.5-P05": "Vị trí đỗ xe không tồn tại hoặc đã bị xóa.",
    "PROP-DEL-01-LAST-MGR": "Không thể xóa tài khoản Quản lý hoạt động cuối cùng trong hệ thống.",
    "PROP-DEL-01-LAST-MGR-EMP": "Không thể xóa nhân viên gắn với tài khoản Quản lý hoạt động cuối cùng.",
    "PROP-DEL-01-SELF": "Tài khoản đang đăng nhập không được phép tự xóa chính mình.",
    "PROP-DEL-01-SELF-EMP": "Nhân viên đang đăng nhập không được phép tự xóa hồ sơ của chính mình.",
    "PROP-DEL-02-ACTIVE-VEH": "Khách hàng đang có phương tiện hoạt động trong hệ thống, không được phép xóa.",
    "PROP-DEL-03-ACTIVE-RSV": "Phương tiện đang có đặt trước vị trí đỗ xe còn hiệu lực, không được phép xóa.",
    "PROP-DEL-03-ACTIVE-TKT": "Phương tiện đang có vé đỗ xe còn hiệu lực, không được phép xóa.",
    "PROP-DEL-03-OPEN-SES": "Phương tiện đang đỗ trong bãi xe (có phiên đỗ đang mở), không được phép xóa.",
    "PROP-DEL-04-OPEN-SES": "Phương tiện liên kết với vé đang đỗ trong bãi xe, không được phép xóa vé.",
    "PROP-DEL-05-OCCUPIED": "Không thể xóa vị trí đỗ xe đang có phương tiện đỗ (trạng thái OCCUPIED).",
    "PROP-DEL-05-RESERVED": "Vị trí đỗ xe đang được đặt trước còn hiệu lực, không được phép xóa.",
    "PROP-DEL-06-FLOOR": "Tầng bãi xe còn khu vực (zone) đang hoạt động, không được phép xóa.",
    "PROP-DEL-06-GATE": "Cổng kiểm soát đang xử lý phiên đỗ xe chưa hoàn thành, không được phép xóa.",
    "PROP-DEL-06-LOT": "Bãi đỗ xe còn tầng đang hoạt động, không được phép xóa.",
    "PROP-DEL-06-POSITION": "Chức vụ đang được phân công cho nhân viên đang hoạt động, không được phép xóa.",
    "PROP-DEL-06-TICKET-TYPE": "Loại vé đang được sử dụng bởi các vé còn hiệu lực, không được phép xóa.",
    "PROP-DEL-06-VEHICLE-TYPE": "Loại xe đang được liên kết với phương tiện đang hoạt động, không được phép xóa.",
    "PROP-DEL-06-ZONE": "Khu vực đỗ xe còn vị trí (slot) đang hoạt động, không được phép xóa.",
    "PROP-DEL-PAYMENT-SETTLED": "Không thể xóa giao dịch thanh toán đã hoàn thành (PAID) hoặc đã hoàn tiền (REFUNDED).",
    "PROP-DEL-SAVT-IN-USE": "Không thể xóa loại xe khỏi vị trí đỗ khi đang có vé, phiên đỗ hoặc đặt chỗ hiệu lực của loại xe này.",
    "PROP-GEN-P01": "Dữ liệu không hợp lệ, xin mời nhập lại dữ liệu",
    "PROP-PAY-SETTLED-IMMUTABLE": "Không thể chỉnh sửa thông tin tài chính hoặc liên kết của chứng từ thanh toán đã hoàn thành (PAID) hoặc đã hoàn tiền (REFUNDED).",
    "PROP-PAY-STATUS-TRANSITION": "Chuyển đổi trạng thái thanh toán không hợp lệ.",
    "PROP-SLOT-VEHICLE-TYPE-MISMATCH": "Loại phương tiện không tương thích với danh sách loại xe cho phép của vị trí đỗ này.",
}

ALL_MESSAGES = {**SRS_MESSAGES, **PROPOSAL_MESSAGES}
MESSAGES = ALL_MESSAGES


def get_srs_message(msg_code: str, default: str = "") -> str:
    """Lấy chuỗi thông báo nguyên văn từ SRS theo mã MSG-*."""
    return SRS_MESSAGES.get(msg_code, default)


def get_prop_message(msg_code: str, default: str = "", **kwargs) -> str:
    """Lấy chuỗi thông báo đề xuất theo mã PROP-* và format biến nếu có."""
    msg = PROPOSAL_MESSAGES.get(msg_code, default)
    if kwargs:
        try:
            return msg.format(**kwargs)
        except Exception:
            return msg
    return msg


def get_message(msg_code: str, default=None, **kwargs) -> str:
    """Truy vấn thông báo tập trung theo bất kỳ mã nào (MSG-* hoặc PROP-*)."""
    if msg_code not in ALL_MESSAGES:
        if default is not None:
            return default
        raise KeyError(f"Unknown message code: {msg_code}")
    msg = ALL_MESSAGES[msg_code]
    if kwargs:
        try:
            return msg.format(**kwargs)
        except Exception:
            return msg
    return msg
