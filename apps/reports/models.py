from django.db import models


class VSlotOccupancyByFloor(models.Model):
    """
    View thống kê tỷ lệ lấp đầy bãi đỗ xe theo tầng và khu vực (v_slot_occupancy_by_floor).
    """

    lot_id = models.BigAutoField(primary_key=True)
    lot_code = models.CharField(max_length=20)
    lot_name = models.CharField(max_length=100)
    floor_id = models.BigIntegerField()
    floor_code = models.CharField(max_length=20)
    floor_name = models.CharField(max_length=50)
    zone_id = models.BigIntegerField()
    zone_code = models.CharField(max_length=20)
    zone_name = models.CharField(max_length=50)
    total_slots = models.BigIntegerField()
    operational_slots = models.BigIntegerField()
    available_slots = models.BigIntegerField()
    occupied_slots = models.BigIntegerField()
    reserved_slots = models.BigIntegerField()
    charging_slots = models.BigIntegerField()
    maintenance_slots = models.BigIntegerField()
    occupancy_rate_pct = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        managed = False
        db_table = "v_slot_occupancy_by_floor"

    def __str__(self):
        return f"{self.lot_code} - {self.floor_code} - {self.zone_code}: {self.occupancy_rate_pct}%"


class VRevenueTodayByMethod(models.Model):
    """
    View thống kê doanh thu hôm nay theo phương thức thanh toán (v_revenue_today_by_method).
    """

    revenue_date = models.DateField(primary_key=True)
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2)
    cash_revenue = models.DecimalField(max_digits=12, decimal_places=2)
    vietqr_revenue = models.DecimalField(max_digits=12, decimal_places=2)
    cash_pct = models.DecimalField(max_digits=5, decimal_places=2)
    vietqr_pct = models.DecimalField(max_digits=5, decimal_places=2)

    class Meta:
        managed = False
        db_table = "v_revenue_today_by_method"

    def __str__(self):
        return f"Revenue {self.revenue_date}: {self.total_revenue}"


class VTrafficByHour(models.Model):
    """
    View thống kê lưu lượng xe vào/ra theo khung giờ (v_traffic_by_hour).
    """

    traffic_hour = models.DateTimeField(primary_key=True)
    entry_count = models.BigIntegerField()
    exit_count = models.BigIntegerField()
    total_movements = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = "v_traffic_by_hour"

    def __str__(self):
        return f"[{self.traffic_hour}] Movements: {self.total_movements}"


class VAiRecognitionStats(models.Model):
    """
    View thống kê độ chính xác nhận diện biển số AI OCR (v_ai_recognition_stats).
    """

    total_sessions = models.BigIntegerField(primary_key=True)
    ai_sessions = models.BigIntegerField()
    manual_sessions = models.BigIntegerField()
    ai_recognition_rate_pct = models.DecimalField(max_digits=5, decimal_places=2)
    manual_rate_pct = models.DecimalField(max_digits=5, decimal_places=2)
    avg_ai_confidence = models.DecimalField(max_digits=5, decimal_places=2)
    active_auto_scan_gates = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = "v_ai_recognition_stats"

    def __str__(self):
        return f"AI Recognition Rate: {self.ai_recognition_rate_pct}% (Sessions: {self.total_sessions})"


class VCustomerStatusSummary(models.Model):
    """
    View tổng hợp trạng thái tài khoản khách hàng (v_customer_status_summary).
    """

    total_customers = models.BigIntegerField(primary_key=True)
    active_customers = models.BigIntegerField()
    suspended_customers = models.BigIntegerField()
    blacklisted_customers = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = "v_customer_status_summary"

    def __str__(self):
        return (
            f"Total Customers: {self.total_customers} (Active: {self.active_customers})"
        )


class VRevenueStatistics(models.Model):
    """
    View thống kê doanh thu theo năm/quý/tháng (v_revenue_statistics).
    """

    report_year = models.IntegerField(primary_key=True)
    report_quarter = models.IntegerField()
    report_month = models.IntegerField()
    total_tickets_sold = models.BigIntegerField()
    total_renewals = models.BigIntegerField()
    total_revenue = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        managed = False
        db_table = "v_revenue_statistics"

    def __str__(self):
        return f"{self.report_year}-M{self.report_month}: {self.total_revenue}"


class VVehicleTrafficDaily(models.Model):
    """
    View thống kê lưu lượng xe vào/ra hàng ngày và số xe đang đỗ (v_vehicle_traffic_daily).
    """

    traffic_date = models.DateField(primary_key=True)
    total_entries = models.BigIntegerField()
    total_exits = models.BigIntegerField()
    currently_parked_count = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = "v_vehicle_traffic_daily"

    def __str__(self):
        return f"{self.traffic_date}: +{self.total_entries} / -{self.total_exits} (Parked: {self.currently_parked_count})"


class VCustomerVehicleSummary(models.Model):
    """
    View tổng hợp phương tiện và vé đỗ xe đang hoạt động theo khách hàng (v_customer_vehicle_summary).
    """

    customer_id = models.BigAutoField(primary_key=True)
    customer_code = models.CharField(max_length=10)
    full_name = models.CharField(max_length=45)
    phone = models.CharField(max_length=15)
    customer_status = models.CharField(max_length=20)
    total_registered_vehicles = models.BigIntegerField()
    total_active_tickets = models.BigIntegerField()

    class Meta:
        managed = False
        db_table = "v_customer_vehicle_summary"

    def __str__(self):
        return f"{self.full_name} ({self.customer_code}): {self.total_registered_vehicles} vehicles"
