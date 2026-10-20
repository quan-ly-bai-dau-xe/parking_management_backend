from django.db import models
from django.utils import timezone


class ActivityLog(models.Model):
    """
    Nhật ký hoạt động kiểm toán hệ thống (bất biến, không xóa mềm, append-only).
    Bảo vệ chống sửa/xóa bởi trigger PostgreSQL trg_activity_log_immutable.
    """

    id = models.BigAutoField(primary_key=True)
    actor_account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="actor_account_id",
        null=True,
        blank=True,
        related_name="activity_logs",
    )
    action = models.CharField(max_length=50)
    entity_type = models.CharField(max_length=50)
    entity_id = models.BigIntegerField(null=True, blank=True)
    message = models.TextField()
    occurred_at = models.DateTimeField(default=timezone.now)

    class Meta:
        managed = False
        db_table = "activity_log"

    def __str__(self):
        return f"[{self.occurred_at}] {self.action} on {self.entity_type} #{self.entity_id}"


class SystemAlert(models.Model):
    """
    Cảnh báo an ninh và bất thường vận hành hệ thống (bất biến, không xóa mềm).
    """

    SEVERITY_CHOICES = [
        ("INFO", "Thông tin"),
        ("WARNING", "Cảnh báo"),
        ("CRITICAL", "Nghiêm trọng"),
    ]

    id = models.BigAutoField(primary_key=True)
    alert_type = models.CharField(max_length=30)
    severity = models.CharField(max_length=20, choices=SEVERITY_CHOICES)
    message = models.TextField()
    entity_type = models.CharField(max_length=50, null=True, blank=True)
    entity_id = models.BigIntegerField(null=True, blank=True)
    occurred_at = models.DateTimeField(default=timezone.now)
    resolved_at = models.DateTimeField(null=True, blank=True)
    resolved_by = models.ForeignKey(
        "employees.Employee",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="resolved_by",
        null=True,
        blank=True,
        related_name="resolved_alerts",
    )
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "system_alert"

    def __str__(self):
        return f"[{self.severity}] {self.alert_type}: {self.message[:30]}"
