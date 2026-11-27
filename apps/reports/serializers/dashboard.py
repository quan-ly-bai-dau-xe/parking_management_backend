"""
Serializers for reports app - Dashboard & Analytics.
Serializes data contracts for Trang chủ — Smart Mobility.png per TL-13, TL-14, and TL-28.6.
"""

from rest_framework import serializers


class SlotKPISerializer(serializers.Serializer):
    """KPI Kho vị trí đỗ xe."""

    total_slots = serializers.IntegerField(
        help_text="Tổng số chỗ đỗ danh định trên toàn bãi"
    )
    operational_slots = serializers.IntegerField(
        help_text="Số chỗ đỗ đang hoạt động (không bảo trì)"
    )
    available_slots = serializers.IntegerField(help_text="Số chỗ đỗ đang còn trống")
    occupied_slots = serializers.IntegerField(help_text="Số chỗ đỗ đang có xe thực tế")
    used_slots = serializers.IntegerField(
        help_text="Tổng số chỗ đỗ đang sử dụng (có xe + đặt trước + sạc điện)"
    )
    occupancy_rate_pct = serializers.FloatField(
        help_text="Tỷ lệ lấp đầy theo phần trăm (%)"
    )
    status_text = serializers.CharField(
        help_text="Trạng thái lấp đầy (Còn chỗ / Gần đầy / Sắp đầy)"
    )


class TrafficKPISerializer(serializers.Serializer):
    """KPI Lưu lượng xe trong ngày."""

    today_entries = serializers.IntegerField(
        help_text="Số lượt xe check-in vào bãi hôm nay"
    )
    today_exits = serializers.IntegerField(
        help_text="Số lượt xe check-out ra khỏi bãi hôm nay"
    )
    active_parking = serializers.IntegerField(
        help_text="Số xe hiện đang đỗ trong bãi (phiên chưa kết thúc)"
    )


class RevenueTodayKPISerializer(serializers.Serializer):
    """KPI Doanh thu hôm nay (chỉ cấp cho Quản lý)."""

    revenue_date = serializers.DateField(help_text="Ngày thống kê doanh thu")
    total_revenue = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Tổng doanh thu thu được hôm nay (VNĐ)",
    )
    cash_revenue = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Doanh thu thanh toán bằng tiền mặt (VNĐ)",
    )
    vietqr_revenue = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Doanh thu thanh toán qua VietQR (VNĐ)",
    )
    cash_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, help_text="Tỷ lệ % doanh thu tiền mặt"
    )
    vietqr_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, help_text="Tỷ lệ % doanh thu VietQR"
    )


class AiRecognitionKPISerializer(serializers.Serializer):
    """KPI Tỷ lệ nhận diện biển số AI."""

    total_sessions = serializers.IntegerField(
        help_text="Tổng số phiên xe quét qua hệ thống"
    )
    ai_sessions = serializers.IntegerField(
        help_text="Số phiên nhận diện tự động thành công bằng AI"
    )
    manual_sessions = serializers.IntegerField(
        help_text="Số phiên cần nhân viên can thiệp nhập tay"
    )
    ai_recognition_rate_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, help_text="Tỷ lệ nhận diện AI tự động (%)"
    )
    manual_rate_pct = serializers.DecimalField(
        max_digits=5, decimal_places=2, help_text="Tỷ lệ nhập tay thủ công (%)"
    )
    avg_ai_confidence = serializers.DecimalField(
        max_digits=5,
        decimal_places=2,
        help_text="Độ tin cậy nhận diện trung bình của AI (0..100)",
    )
    active_auto_scan_gates = serializers.IntegerField(
        help_text="Số cổng kiểm soát quét tự động đang hoạt động"
    )


class DashboardSummaryKPISerializer(serializers.Serializer):
    """Tổng hợp 4 nhóm KPI trên đầu Trang chủ."""

    slots = SlotKPISerializer()
    traffic = TrafficKPISerializer()
    revenue = RevenueTodayKPISerializer(
        required=False,
        allow_null=True,
        help_text="Doanh thu hôm nay (None nếu không phải Manager)",
    )
    ai_recognition = AiRecognitionKPISerializer()


class FloorOccupancyBarSerializer(serializers.Serializer):
    """Thanh tỷ lệ lấp đầy theo tầng per TL-28.6."""

    floor_id = serializers.IntegerField(help_text="ID của tầng")
    floor_code = serializers.CharField(help_text="Mã tầng (ví dụ: B1, B2, B3)")
    floor_name = serializers.CharField(help_text="Tên tầng hiển thị (ví dụ: Tầng B1)")
    total_slots = serializers.IntegerField(help_text="Tổng số chỗ đỗ của tầng")
    operational_slots = serializers.IntegerField(help_text="Số chỗ đỗ đang hoạt động")
    used_slots = serializers.IntegerField(help_text="Số chỗ đỗ đang sử dụng")
    available_slots = serializers.IntegerField(help_text="Số chỗ đỗ đang trống")
    occupancy_percentage = serializers.FloatField(help_text="Tỷ lệ lấp đầy (%)")
    status_badge = serializers.CharField(
        help_text="Huy hiệu trạng thái ('Còn chỗ' hoặc 'Sắp đầy')"
    )
    fe_display_label = serializers.CharField(
        help_text="Nhãn hiển thị trực tiếp cho Frontend (ví dụ: 'Tầng B1 · 92% (184/200 chỗ)')"
    )


class TrafficHourPointSerializer(serializers.Serializer):
    """Điểm dữ liệu biểu đồ lưu lượng theo giờ (24h)."""

    traffic_hour = serializers.DateTimeField(
        help_text="Mốc giờ thống kê (UTC / ISO 8601)"
    )
    entry_count = serializers.IntegerField(help_text="Số lượt xe vào trong giờ này")
    exit_count = serializers.IntegerField(help_text="Số lượt xe ra trong giờ này")
    total_movements = serializers.IntegerField(
        help_text="Tổng số lượt di chuyển vào + ra"
    )


class EmergencyAlertSerializer(serializers.Serializer):
    """Cảnh báo khẩn cấp / bất thường từ system_alert per TL-13."""

    id = serializers.IntegerField(help_text="Mã định danh cảnh báo")
    alert_type = serializers.CharField(
        help_text="Loại cảnh báo (BLACKLIST_PLATE, OVERSTAY, CAMERA_QUALITY, ...)"
    )
    severity = serializers.CharField(
        help_text="Mức độ nghiêm trọng (INFO, WARNING, CRITICAL)"
    )
    message = serializers.CharField(help_text="Nội dung thông báo cảnh báo")
    entity_type = serializers.CharField(
        required=False, allow_null=True, help_text="Thực thể liên quan"
    )
    entity_id = serializers.IntegerField(
        required=False, allow_null=True, help_text="ID thực thể liên quan"
    )
    occurred_at = serializers.DateTimeField(help_text="Thời điểm xảy ra cảnh báo")
    resolved_at = serializers.DateTimeField(
        required=False, allow_null=True, help_text="Thời điểm đã xử lý xong"
    )


class RecentActivitySerializer(serializers.Serializer):
    """Nhật ký hoạt động xe ra vào gần nhất."""

    id = serializers.IntegerField(help_text="ID của phiên đỗ xe")
    session_code = serializers.CharField(help_text="Mã phiên đỗ xe (#PK-...)")
    license_plate = serializers.CharField(help_text="Biển số xe")
    direction = serializers.CharField(help_text="Hướng di chuyển ('IN' hoặc 'OUT')")
    timestamp = serializers.DateTimeField(help_text="Thời gian xe vào hoặc ra")
    fee_amount = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        help_text="Cước phí phiên đỗ (nếu đã thanh toán/check-out)",
    )
    recognition_source = serializers.CharField(
        help_text="Phương thức nhận diện (AI hoặc MANUAL)"
    )


class DashboardOverviewResponseSerializer(serializers.Serializer):
    """Schema tổng hợp toàn bộ dữ liệu cần thiết cho Trang chủ — Smart Mobility."""

    kpis = DashboardSummaryKPISerializer(help_text="4 nhóm thẻ KPI đầu trang")
    floors = FloorOccupancyBarSerializer(
        many=True, help_text="Thanh tỷ lệ lấp đầy theo tầng (B1, B2, B3)"
    )
    traffic_chart = TrafficHourPointSerializer(
        many=True, help_text="Biểu đồ lưu lượng xe vào / ra 24h"
    )
    alerts = EmergencyAlertSerializer(
        many=True, help_text="Danh sách cảnh báo khẩn cấp và bất thường"
    )
    recent_activities = RecentActivitySerializer(
        many=True, help_text="Danh sách hoạt động xe ra vào gần nhất"
    )
