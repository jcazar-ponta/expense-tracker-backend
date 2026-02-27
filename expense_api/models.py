import uuid

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models

month_validator = RegexValidator(
    regex=r"^\d{4}-(0[1-9]|1[0-2])$",
    message="Month must be in YYYY-MM format.",
)


class SplitType(models.TextChoices):
    EQUAL = "EQUAL", "EQUAL"
    CUSTOM_AMOUNT = "CUSTOM_AMOUNT", "CUSTOM_AMOUNT"
    PERCENT = "PERCENT", "PERCENT"
    SHARES = "SHARES", "SHARES"


class PaymentStatus(models.TextChoices):
    UNPAID = "UNPAID", "UNPAID"
    PARTIAL = "PARTIAL", "PARTIAL"
    PAID = "PAID", "PAID"


class EntityType(models.TextChoices):
    PERSON = "PERSON", "PERSON"
    ITEM = "ITEM", "ITEM"
    PAYMENT = "PAYMENT", "PAYMENT"
    SETTINGS = "SETTINGS", "SETTINGS"


class ActionType(models.TextChoices):
    CREATE = "CREATE", "CREATE"
    UPDATE = "UPDATE", "UPDATE"
    DELETE = "DELETE", "DELETE"
    MARK_PAID = "MARK_PAID", "MARK_PAID"
    IMPORT = "IMPORT", "IMPORT"
    EXPORT = "EXPORT", "EXPORT"


class RoundingStrategy(models.TextChoices):
    ROUND_TO_CENT = "ROUND_TO_CENT", "ROUND_TO_CENT"
    DISTRIBUTE_REMAINDER = "DISTRIBUTE_REMAINDER", "DISTRIBUTE_REMAINDER"


class BaseOwnedModel(models.Model):
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="%(class)ss")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Person(BaseOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField(max_length=255)
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["created_at"]


class ItemExpense(BaseOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    title = models.CharField(max_length=255)
    category = models.CharField(max_length=255)
    notes = models.TextField(blank=True, default="")
    total_amount = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0.01)])
    currency = models.CharField(max_length=16)
    purchase_date = models.DateField()
    installment_months = models.PositiveIntegerField(validators=[MinValueValidator(1), MaxValueValidator(60)])
    start_month = models.CharField(max_length=7, validators=[month_validator])
    split_type = models.CharField(max_length=20, choices=SplitType.choices)

    class Meta:
        ordering = ["-created_at"]


class Allocation(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    item = models.ForeignKey(ItemExpense, on_delete=models.CASCADE, related_name="allocations")
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="allocations")
    value = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        unique_together = ("item", "person")
        ordering = ["item_id", "person_id"]


class Payment(BaseOwnedModel):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    person = models.ForeignKey(Person, on_delete=models.CASCADE, related_name="payments")
    month = models.CharField(max_length=7, validators=[month_validator], db_index=True)
    amount_paid = models.DecimalField(max_digits=12, decimal_places=2, validators=[MinValueValidator(0)])
    status = models.CharField(max_length=10, choices=PaymentStatus.choices, default=PaymentStatus.UNPAID)
    paid_at = models.DateTimeField(null=True, blank=True)
    method = models.CharField(max_length=255, blank=True, null=True)
    notes = models.TextField(blank=True, null=True)

    class Meta:
        ordering = ["-updated_at"]
        constraints = [
            models.UniqueConstraint(fields=["owner", "person", "month"], name="unique_owner_person_month_payment")
        ]


class LedgerEvent(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    owner = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ledger_events")
    ts = models.DateTimeField()
    actor = models.CharField(max_length=255)
    entity_type = models.CharField(max_length=16, choices=EntityType.choices)
    entity_id = models.CharField(max_length=255)
    action = models.CharField(max_length=16, choices=ActionType.choices)
    diff = models.JSONField(null=True, blank=True)

    class Meta:
        ordering = ["-ts"]


class AppSettings(models.Model):
    owner = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="app_settings")
    default_currency = models.CharField(max_length=16, default="PHP")
    rounding_strategy = models.CharField(
        max_length=32,
        choices=RoundingStrategy.choices,
        default=RoundingStrategy.DISTRIBUTE_REMAINDER,
    )
