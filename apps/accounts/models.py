from django.contrib.auth.models import (
    AbstractBaseUser,
    BaseUserManager,
    Group,
    Permission,
    PermissionsMixin,
)
from django.core.validators import RegexValidator
from django.db import models


class AccountManager(BaseUserManager):
    def create_user(self, username, password=None, **extra_fields):
        if not username:
            raise ValueError("The Username field must be set")
        username = self.model.normalize_username(username)
        user = self.model(username=username, **extra_fields)
        if password:
            user.set_password(password)
        user.save(using=self._db)
        return user

    def create_superuser(self, username, password=None, **extra_fields):
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")
        return self.create_user(username, password, **extra_fields)


class Account(AbstractBaseUser, PermissionsMixin):
    # Username validation: no special characters per SRS 4.1-F01
    username_validator = RegexValidator(
        r"^[a-zA-Z0-9_.-]+$", "Tên đăng nhập không chứa ký tự đặc biệt", "invalid"
    )

    id = models.BigAutoField(primary_key=True)
    username = models.CharField(
        "Tên đăng nhập",
        max_length=50,
        unique=True,
        validators=[username_validator],
        help_text="Nhập tên đăng nhập được admin cấp điền vào để đăng nhập hệ thống. So sánh ở ACCOUNT.TenDangNhap. Không chứa ký tự đặc biệt.",
    )
    password_hash = models.CharField("Mật khẩu", max_length=255)
    role_choices = [
        ("MANAGER", "Quản lý"),
        ("EMPLOYEE", "Nhân viên"),
        ("CUSTOMER", "Khách hàng"),
    ]
    role = models.CharField(
        max_length=20,
        choices=role_choices,
        default="EMPLOYEE",
        help_text="RBAC authorization role: MANAGER (Quản lý), EMPLOYEE (Nhân viên), CUSTOMER [PROPOSAL] (Khách hàng per OQ-03, OQ-54)",
    )
    is_active = models.BooleanField(
        "Trạng thái kích hoạt",
        default=True,
        help_text="Account activation status: TRUE (Active), FALSE (Disabled) (SRS 4.1, ADR-0004)",
    )
    is_staff = models.BooleanField(
        default=False,
        help_text="Designates whether the user can log into this admin site.",
    )
    is_superuser = models.BooleanField(
        default=False,
        help_text="Designates that this user has all permissions without explicitly assigning them.",
    )
    last_login = models.DateTimeField(
        null=True,
        blank=True,
        help_text="Timestamp of most recent successful authentication (SRS 4.1, ADR-0004)",
    )
    row_version = models.IntegerField(default=1)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    deleted_at = models.DateTimeField(null=True, blank=True)
    deleted_by = models.ForeignKey(
        "self",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="deleted_accounts",
    )

    # Override groups and user_permissions to avoid clashes with auth.User
    groups: models.ManyToManyField[Group, Account] = models.ManyToManyField(  # type: ignore[assignment]
        "auth.Group",
        verbose_name="groups",
        blank=True,
        help_text="The groups this user belongs to. A user will get all permissions granted to each of their groups.",
        related_name="account_set",
        related_query_name="account",
    )
    user_permissions: models.ManyToManyField[Permission, Account] = (
        models.ManyToManyField(  # type: ignore[assignment]
            "auth.Permission",
            verbose_name="user permissions",
            blank=True,
            help_text="Specific permissions for this user.",
            related_name="account_set",
            related_query_name="account",
        )
    )

    objects = AccountManager()

    USERNAME_FIELD = "username"
    REQUIRED_FIELDS = []

    class Meta:
        db_table = "account"
        verbose_name = "Tài khoản"
        verbose_name_plural = "Tài khoản"
        indexes = [
            models.Index(
                fields=["username"],
                name="uq_account_username_active",
                condition=models.Q(deleted_at__isnull=True),
            ),
            models.Index(
                fields=["role"],
                name="idx_account_role",
                condition=models.Q(deleted_at__isnull=True),
            ),
        ]

    def __str__(self):
        return self.username

    def clean(self):
        # Ensure username doesn't contain special characters
        if self.username and not self.username_validator.regex.search(self.username):
            from django.core.exceptions import ValidationError

            raise ValidationError(
                {"username": "Tên đăng nhập không chứa ký tự đặc biệt"}
            )

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)


class PersistentLoginToken(models.Model):
    id = models.BigAutoField(primary_key=True)
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="persistent_tokens"
    )
    series = models.CharField(max_length=64, unique=True)
    token_hash = models.CharField(max_length=255)
    ip_address = models.GenericIPAddressField(null=True, blank=True)
    user_agent = models.TextField(null=True, blank=True)
    expires_at = models.DateTimeField()
    created_at = models.DateTimeField(auto_now_add=True)
    last_used_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "persistent_login_token"
        verbose_name = "Token ghi nhớ đăng nhập"
        verbose_name_plural = "Tokens ghi nhớ đăng nhập"
        indexes = [
            models.Index(fields=["account"], name="idx_persistent_token_account"),
            models.Index(fields=["expires_at"], name="idx_persistent_token_expires"),
        ]

    def __str__(self):
        return f"{self.account.username} - {self.series}"


class PasswordResetToken(models.Model):
    id = models.BigAutoField(primary_key=True)
    account = models.ForeignKey(
        Account, on_delete=models.PROTECT, related_name="password_reset_tokens"
    )
    token_hash = models.CharField(max_length=255, unique=True)
    expires_at = models.DateTimeField()
    is_used = models.BooleanField(default=False)
    used_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "password_reset_token"
        verbose_name = "Token đặt lại mật khẩu"
        verbose_name_plural = "Tokens đặt lại mật khẩu"
        indexes = [
            models.Index(fields=["account"], name="idx_password_reset_account"),
        ]

    def __str__(self):
        return f"{self.account.username} - reset token"
