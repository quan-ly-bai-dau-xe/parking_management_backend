from django.core.exceptions import PermissionDenied
from django.db import models
from django.db.models.lookups import IsNull
from django.db.models.sql.where import WhereNode
from django.utils import timezone


def _has_deleted_at_lookup(node):
    """Kiểm tra đệ quy xem cây điều kiện WHERE có chứa lookup trên cột deleted_at hay không."""
    for child in getattr(node, "children", []):
        if isinstance(child, WhereNode) and _has_deleted_at_lookup(child):
            return True
        if (
            isinstance(child, IsNull)
            and hasattr(child.lhs, "target")
            and child.lhs.target.name == "deleted_at"
        ):
            return True
    return False


def _transform_deleted_at_where(node, mode="only_deleted"):
    """
    Biến đổi cây điều kiện WHERE của Django ORM một cách an toàn.
    - mode='only_deleted': Chuyển đổi IsNull(deleted_at, True) thành IsNull(deleted_at, False).
    - mode='with_deleted': Gỡ bỏ các node lookup IsNull trên deleted_at.
    """
    new_children = []
    for child in getattr(node, "children", []):
        if isinstance(child, WhereNode):
            transformed = _transform_deleted_at_where(child, mode)
            if transformed.children:
                new_children.append(transformed)
        elif (
            isinstance(child, IsNull)
            and hasattr(child.lhs, "target")
            and child.lhs.target.name == "deleted_at"
        ):
            if mode == "only_deleted":
                new_children.append(IsNull(child.lhs, False))
            elif mode == "with_deleted":
                pass  # Bỏ qua để loại bỏ bộ lọc
        else:
            new_children.append(child)
    return node.__class__(new_children, connector=node.connector, negated=node.negated)


class SoftDeleteQuerySet(models.QuerySet):
    """
    QuerySet tùy chỉnh cấm thao tác xóa cứng và cung cấp các phương thức lọc thùng rác an toàn per ADR-0003 & TL-23..TL-26.
    """

    def delete(self):
        return self.soft_delete()

    def hard_delete(self):
        raise PermissionDenied(
            "Thao tác xóa cứng trên thực thể nghiệp vụ bị nghiêm cấm per ADR-0003."
        )

    def soft_delete(self, user=None):
        user_id = user.id if hasattr(user, "id") else user
        return self.update(deleted_at=timezone.now(), deleted_by_id=user_id)

    def restore(self):
        """
        Khôi phục các bản ghi đã xóa mềm bằng cách đặt deleted_at=None, deleted_by=None.
        Tự động nhắm đúng các bản ghi trong thùng rác (deleted_at IS NOT NULL)
        ngay cả khi QuerySet được gọi từ default manager (.objects) hoặc đã qua bộ lọc.
        """
        return self.only_deleted().update(deleted_at=None, deleted_by_id=None)

    def with_deleted(self):
        """
        Bao gồm cả bản ghi đang hoạt động lẫn bản ghi đã bị xóa mềm.
        Gỡ bỏ điều kiện lọc deleted_at nếu đã tồn tại trong QuerySet.
        """
        clone = self._chain()
        if _has_deleted_at_lookup(clone.query.where):
            clone.query.where = _transform_deleted_at_where(
                clone.query.where, mode="with_deleted"
            )
        return clone

    def only_deleted(self):
        """
        Chỉ lọc các bản ghi đã bị xóa mềm (thùng rác).
        Nếu QuerySet đã có filter deleted_at__isnull=True, tự động chuyển thành False.
        Nếu QuerySet chưa có điều kiện deleted_at, bổ sung filter deleted_at__isnull=False.
        """
        clone = self._chain()
        if _has_deleted_at_lookup(clone.query.where):
            clone.query.where = _transform_deleted_at_where(
                clone.query.where, mode="only_deleted"
            )
            return clone
        return clone.filter(deleted_at__isnull=False)


class SoftDeleteManager(models.Manager):
    """
    Manager mặc định chỉ trả về các bản ghi chưa bị xóa mềm (deleted_at IS NULL),
    đồng thời kế thừa toàn bộ phương thức của SoftDeleteQuerySet.
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
        return SoftDeleteQuerySet(self.model, using=self._db).restore()

    def soft_delete(self, user=None):
        return SoftDeleteQuerySet(self.model, using=self._db).soft_delete(user=user)

    def hard_delete(self):
        return SoftDeleteQuerySet(self.model, using=self._db).hard_delete()


class TimeStampedModel(models.Model):
    """
    Lớp trừu tượng cơ sở cung cấp dấu vết thời gian tạo và cập nhật.
    Tự động áp dụng cho các bảng có cả created_at và updated_at.
    """

    created_at = models.DateTimeField(default=timezone.now, editable=False)
    updated_at = models.DateTimeField(default=timezone.now, editable=False)

    class Meta:
        abstract = True


class SoftDeleteBaseModel(models.Model):
    """
    Lớp trừu tượng cơ sở quản lý vòng đời xóa mềm theo ADR-0003 và TL-45.
    Chỉ bao gồm các trường và phương thức phục vụ xóa mềm.
    """

    deleted_at = models.DateTimeField(null=True, blank=True, editable=False)
    deleted_by = models.ForeignKey(
        "accounts.Account",
        on_delete=models.DO_NOTHING,
        db_column="deleted_by",
        db_constraint=False,
        null=True,
        blank=True,
        related_name="+",
        editable=False,
    )

    objects = SoftDeleteManager()
    all_objects = SoftDeleteQuerySet.as_manager()

    class Meta:
        abstract = True

    def delete(self, using=None, keep_parents=False):
        return self.soft_delete()

    def hard_delete(self):
        raise PermissionDenied(
            "Hard delete bị nghiêm cấm per ADR-0003. Hãy dùng soft_delete()."
        )

    def soft_delete(self, user=None):
        self.deleted_at = timezone.now()
        self.deleted_by = user
        self.save(update_fields=["deleted_at", "deleted_by"])

    def restore(self):
        self.deleted_at = None
        self.deleted_by = None
        self.save(update_fields=["deleted_at", "deleted_by"])


class SoftDeleteModel(TimeStampedModel, SoftDeleteBaseModel):
    """
    Lớp trừu tượng chuẩn cho 17 thực thể nghiệp vụ xóa mềm có đầy đủ timestamps:
    created_at, updated_at, deleted_at, deleted_by.
    """

    class Meta:
        abstract = True


# ==============================================================================
# Danh mục Địa giới Hành chính (3 Bảng Unmanaged)
# ==============================================================================


class AdministrativeProvince(TimeStampedModel):
    """
    Tỉnh / Thành phố trực thuộc trung ương (bất biến, không xóa mềm).
    """

    id = models.BigAutoField(primary_key=True)
    code = models.CharField(max_length=20, unique=True)
    name = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = "administrative_province"

    def __str__(self):
        return self.name


class AdministrativeDistrict(TimeStampedModel):
    """
    Quận / Huyện / Thị xã (bất biến, không xóa mềm).
    """

    id = models.BigAutoField(primary_key=True)
    province = models.ForeignKey(
        AdministrativeProvince,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="province_id",
        related_name="districts",
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = "administrative_district"

    def __str__(self):
        return f"{self.name}, {self.province.name}"


class AdministrativeWard(TimeStampedModel):
    """
    Xã / Phường / Thị trấn (bất biến, không xóa mềm).
    """

    id = models.BigAutoField(primary_key=True)
    district = models.ForeignKey(
        AdministrativeDistrict,
        on_delete=models.DO_NOTHING,
        db_constraint=False,
        db_column="district_id",
        related_name="wards",
    )
    code = models.CharField(max_length=20)
    name = models.CharField(max_length=100)

    class Meta:
        managed = False
        db_table = "administrative_ward"

    def __str__(self):
        return f"{self.name}, {self.district.name}"
