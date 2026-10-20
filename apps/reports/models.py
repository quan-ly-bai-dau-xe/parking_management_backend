from django.conf import settings
from django.db import models


class Report(models.Model):
    REPORT_TYPE_CHOICES = [
        ("revenue", "הכנסות"),
        ("volume", "נפח"),
        ("occupancy", "תפוסה"),
    ]

    FORMAT_CHOICES = [
        ("pdf", "PDF"),
        ("excel", "Excel"),
        ("csv", "CSV"),
    ]

    id = models.BigAutoField(primary_key=True)
    title = models.CharField(max_length=255)
    report_type = models.CharField(max_length=20, choices=REPORT_TYPE_CHOICES)
    format = models.CharField(max_length=10, choices=FORMAT_CHOICES)
    parameters = models.JSONField(
        null=True,
        blank=True,
        help_text="Parameters used to generate the report (date ranges, filters, etc.)",
    )
    generated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="generated_reports",
    )
    generated_at = models.DateTimeField(auto_now_add=True)
    file_path = models.CharField(
        max_length=500,
        null=True,
        blank=True,
        help_text="Path to the generated report file",
    )
    is_active = models.BooleanField(default=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="deleted_reports",
    )

    class Meta:
        db_table = "reports_report"
        verbose_name = "דוח"
        verbose_name_plural = "דוחות"
        indexes = [
            models.Index(fields=["report_type"]),
            models.Index(fields=["generated_at"]),
            models.Index(fields=["generated_by"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.get_report_type_display()})"
