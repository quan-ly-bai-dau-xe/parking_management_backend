from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteBaseModel, SoftDeleteModel


class News(SoftDeleteModel):
    """
    Tin tức bãi đỗ xe và thông báo công khai (có xóa mềm).
    """

    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=200)
    slug = models.CharField(max_length=220, unique=True)
    summary = models.CharField(max_length=500, null=True, blank=True)
    content = models.TextField()
    thumbnail_url = models.TextField(null=True, blank=True)
    author = models.ForeignKey(
        "employees.Employee",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="author_id",
        related_name="news",
    )
    is_published = models.BooleanField(default=False)
    published_at = models.DateTimeField(null=True, blank=True)
    view_count = models.IntegerField(default=0)
    row_version = models.IntegerField(default=1, editable=False)

    class Meta:
        managed = False
        db_table = "news"

    def __str__(self):
        return self.title


class Notification(SoftDeleteBaseModel):
    """
    Thông báo hệ thống gửi đến người dùng (có xóa mềm).
    Bảng notification trong Schema v2 không có updated_at, do đó kế thừa SoftDeleteBaseModel.
    """

    NOTIFICATION_TYPE_CHOICES = [
        ("SYSTEM", "Hệ thống"),
        ("ALERT", "Cảnh báo an ninh"),
        ("TICKET", "Thông báo vé xe"),
        ("PAYMENT", "Thông báo thanh toán"),
    ]

    id = models.BigAutoField(primary_key=True)
    recipient_account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="recipient_account_id",
        null=True,
        blank=True,
        related_name="notifications",
    )
    title = models.CharField(max_length=200)
    content = models.TextField()
    notification_type = models.CharField(
        max_length=30,
        choices=NOTIFICATION_TYPE_CHOICES,
        default="SYSTEM",
    )
    is_read = models.BooleanField(default=False)
    read_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "notification"

    def __str__(self):
        return self.title
