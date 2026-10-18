from django.contrib.auth.models import AbstractBaseUser, BaseUserManager
from django.db import models
from django.utils import timezone

from apps.core.models import SoftDeleteManager, SoftDeleteModel, SoftDeleteQuerySet


class AccountManager(BaseUserManager, SoftDeleteManager):
    """
    Manager cho Account với đăng nhập linh hoạt bằng email hoặc số điện thoại,
    mặc định lọc bản ghi chưa bị xóa mềm và đồng bộ hành vi SoftDelete.
    """

    def get_queryset(self):
        return SoftDeleteQuerySet(self.model, using=self._db).filter(
            deleted_at__isnull=True
        )

    def with_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db).with_deleted()

    def only_deleted(self):
        return SoftDeleteQuerySet(self.model, using=self._db).only_deleted()

    def restore(self):
        return self.get_queryset().restore()

    def soft_delete(self, user=None):
        return self.get_queryset().soft_delete(user=user)

    def create_user(
        self, email=None, phone=None, password=None, role="EMPLOYEE", **extra_fields
    ):
        if not email and not phone:
            raise ValueError("Bắt buộc phải cung cấp Email hoặc Số điện thoại.")
        email = self.normalize_email(email) if email else None
        user = self.model(email=email, phone=phone, role=role, **extra_fields)
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()
        user.save(using=self._db)
        return user

    def create_superuser(self, email=None, phone=None, password=None, **extra_fields):
        extra_fields.setdefault("role", "MANAGER")
        extra_fields.setdefault("is_active", True)
        return self.create_user(
            email=email, phone=phone, password=password, **extra_fields
        )


class Account(AbstractBaseUser, SoftDeleteModel):
    """
    Tài khoản xác thực hệ thống (AUTH_USER_MODEL).
    Không dùng PermissionsMixin để tránh phát sinh cột ảo ngoài CSDL Schema v2.
    """

    ROLE_CHOICES = [
        ("MANAGER", "Quản lý"),
        ("EMPLOYEE", "Nhân viên"),
        ("CUSTOMER", "Khách hàng"),
    ]

    id = models.BigAutoField(primary_key=True)
    email = models.CharField(max_length=100, unique=True, null=True, blank=True)
    phone = models.CharField(max_length=15, null=True, blank=True)
    password = models.CharField(max_length=255, db_column="password_hash")
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default="EMPLOYEE")
    is_active = models.BooleanField(default=True)
    last_login = models.DateTimeField(null=True, blank=True, db_column="last_login_at")
    row_version = models.IntegerField(default=1, editable=False)

    objects = AccountManager()  # type: ignore[misc]
    all_objects = SoftDeleteQuerySet.as_manager()  # type: ignore[misc]

    USERNAME_FIELD = "email"
    REQUIRED_FIELDS = []

    class Meta:
        managed = False
        db_table = "account"

    def __str__(self):
        return self.email or self.phone or f"Account #{self.id}"

    @property
    def is_staff(self):
        return self.role == "MANAGER"

    @property
    def is_superuser(self):
        return self.role == "MANAGER"

    def has_perm(self, perm, obj=None):
        return self.role == "MANAGER"

    def has_module_perms(self, app_label):
        return self.role == "MANAGER"


class PersistentLoginToken(models.Model):
    """
    Token ghi nhớ đăng nhập (Remember-Me) theo chuẩn OWASP (ADR-0004 & TL-36).
    Cho phép xóa cứng (plain delete) để hỗ trợ xoay vòng và thu hồi token.
    """

    id = models.BigAutoField(primary_key=True)
    series = models.CharField(max_length=64, unique=True)
    token_hash = models.CharField(max_length=255)
    account = models.ForeignKey(
        Account,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="account_id",
        related_name="persistent_tokens",
    )
    ip_address = models.CharField(max_length=45, null=True, blank=True)
    user_agent = models.CharField(max_length=255, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)
    last_used_at = models.DateTimeField(default=timezone.now)
    expires_at = models.DateTimeField()

    class Meta:
        managed = False
        db_table = "persistent_login_token"

    def __str__(self):
        return f"Token series {self.series} for Account #{self.account_id}"


class PasswordResetToken(models.Model):
    """
    Token đặt lại mật khẩu một lần (ADR-0004 & TL-36).
    Cho phép xóa cứng (plain delete).
    """

    id = models.BigAutoField(primary_key=True)
    account = models.ForeignKey(
        Account,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="account_id",
        related_name="password_reset_tokens",
    )
    token_hash = models.CharField(max_length=255)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True, blank=True)
    requested_ip = models.CharField(max_length=45, null=True, blank=True)
    created_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        managed = False
        db_table = "password_reset_token"

    def __str__(self):
        return f"ResetToken #{self.id} for Account #{self.account_id}"
