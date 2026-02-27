from datetime import timedelta
from uuid import UUID

from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import (
    ActionType,
    Allocation,
    AppSettings,
    EntityType,
    ItemExpense,
    LedgerEvent,
    Payment,
    Person,
    PublicShareLink,
    ShareScopeType,
)
from .services.share_tokens import generate_share_token, hash_share_token
from .utils import to_json_safe


class OwnedModelSerializer(serializers.ModelSerializer):
    createdAt = serializers.DateTimeField(source="created_at", read_only=True)
    updatedAt = serializers.DateTimeField(source="updated_at", read_only=True)


class PersonSerializer(OwnedModelSerializer):
    isActive = serializers.BooleanField(source="is_active")

    class Meta:
        model = Person
        fields = ("id", "name", "isActive", "createdAt", "updatedAt")


class AllocationSerializer(serializers.ModelSerializer):
    personId = serializers.UUIDField(source="person_id")
    value = serializers.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        model = Allocation
        fields = ("personId", "value")

    def validate_personId(self, value):
        request = self.context["request"]
        if not Person.objects.filter(id=value, owner=request.user).exists():
            raise serializers.ValidationError("personId must reference one of your people.")
        return value


class ItemExpenseSerializer(OwnedModelSerializer):
    totalAmount = serializers.DecimalField(source="total_amount", max_digits=12, decimal_places=2)
    purchaseDate = serializers.DateField(source="purchase_date")
    installmentMonths = serializers.IntegerField(source="installment_months")
    startMonth = serializers.CharField(source="start_month")
    splitType = serializers.CharField(source="split_type")
    allocations = AllocationSerializer(many=True)

    class Meta:
        model = ItemExpense
        fields = (
            "id",
            "title",
            "category",
            "notes",
            "totalAmount",
            "currency",
            "purchaseDate",
            "installmentMonths",
            "startMonth",
            "splitType",
            "allocations",
            "createdAt",
            "updatedAt",
        )

    def validate_allocations(self, value):
        if len(value) == 0:
            raise serializers.ValidationError("At least one allocation is required.")
        return value

    def validate(self, attrs):
        split_type = attrs.get("split_type", getattr(self.instance, "split_type", None))
        allocations = attrs.get("allocations")
        if allocations is not None and split_type == "EQUAL":
            for alloc in allocations:
                if alloc["value"] <= 0:
                    raise serializers.ValidationError(
                        {"allocations": "EQUAL split requires positive allocation values."}
                    )
        return attrs

    @transaction.atomic
    def create(self, validated_data):
        allocations_data = validated_data.pop("allocations")
        item = ItemExpense.objects.create(owner=self.context["request"].user, **validated_data)
        self._replace_allocations(item, allocations_data)
        self._create_ledger(item.owner, EntityType.ITEM, str(item.id), ActionType.CREATE, validated_data)
        return item

    @transaction.atomic
    def update(self, instance, validated_data):
        allocations_data = validated_data.pop("allocations", None)
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        if allocations_data is not None:
            self._replace_allocations(instance, allocations_data)
        self._create_ledger(instance.owner, EntityType.ITEM, str(instance.id), ActionType.UPDATE, validated_data)
        return instance

    def _replace_allocations(self, item, allocations_data):
        Allocation.objects.filter(item=item).delete()
        allocations = [
            Allocation(item=item, person_id=alloc["person_id"], value=alloc["value"])
            for alloc in allocations_data
        ]
        Allocation.objects.bulk_create(allocations)

    def _create_ledger(self, owner, entity_type, entity_id, action, diff):
        LedgerEvent.objects.create(
            owner=owner,
            ts=timezone.now(),
            actor=owner.email or owner.username,
            entity_type=entity_type,
            entity_id=entity_id,
            action=action,
            diff=to_json_safe(diff) if diff else None,
        )


class PaymentSerializer(OwnedModelSerializer):
    personId = serializers.UUIDField(source="person_id")
    amountPaid = serializers.DecimalField(source="amount_paid", max_digits=12, decimal_places=2)
    paidAt = serializers.DateTimeField(source="paid_at", required=False, allow_null=True)

    class Meta:
        model = Payment
        fields = (
            "id",
            "personId",
            "month",
            "amountPaid",
            "status",
            "paidAt",
            "method",
            "notes",
            "createdAt",
            "updatedAt",
        )

    def validate_personId(self, value):
        request = self.context["request"]
        if not Person.objects.filter(id=value, owner=request.user).exists():
            raise serializers.ValidationError("personId must reference one of your people.")
        return value

    def create(self, validated_data):
        payment = Payment.objects.create(owner=self.context["request"].user, **validated_data)
        LedgerEvent.objects.create(
            owner=payment.owner,
            ts=payment.created_at,
            actor=payment.owner.email or payment.owner.username,
            entity_type=EntityType.PAYMENT,
            entity_id=str(payment.id),
            action=ActionType.CREATE,
            diff=to_json_safe(validated_data),
        )
        return payment

    def update(self, instance, validated_data):
        for key, value in validated_data.items():
            setattr(instance, key, value)
        instance.save()
        LedgerEvent.objects.create(
            owner=instance.owner,
            ts=instance.updated_at,
            actor=instance.owner.email or instance.owner.username,
            entity_type=EntityType.PAYMENT,
            entity_id=str(instance.id),
            action=ActionType.UPDATE,
            diff=to_json_safe(validated_data),
        )
        return instance


class LedgerEventSerializer(serializers.ModelSerializer):
    entityType = serializers.CharField(source="entity_type")
    entityId = serializers.CharField(source="entity_id")

    class Meta:
        model = LedgerEvent
        fields = ("id", "ts", "actor", "entityType", "entityId", "action", "diff")


class AppSettingsSerializer(serializers.ModelSerializer):
    defaultCurrency = serializers.CharField(source="default_currency")
    roundingStrategy = serializers.CharField(source="rounding_strategy")

    class Meta:
        model = AppSettings
        fields = ("defaultCurrency", "roundingStrategy")


class PublicShareLinkSerializer(OwnedModelSerializer):
    scopeType = serializers.CharField(source="scope_type")
    scopePayload = serializers.JSONField(source="scope_payload")
    expiresAt = serializers.DateTimeField(source="expires_at", allow_null=True)
    revokedAt = serializers.DateTimeField(source="revoked_at", allow_null=True)
    lastAccessedAt = serializers.DateTimeField(source="last_accessed_at", allow_null=True)
    accessCount = serializers.IntegerField(source="access_count")

    class Meta:
        model = PublicShareLink
        fields = (
            "id",
            "scopeType",
            "scopePayload",
            "permissions",
            "expiresAt",
            "revokedAt",
            "lastAccessedAt",
            "accessCount",
            "createdAt",
            "updatedAt",
        )


class PublicShareLinkCreateSerializer(serializers.Serializer):
    scopeType = serializers.ChoiceField(choices=ShareScopeType.choices)
    scopePayload = serializers.JSONField()
    expiresInDays = serializers.IntegerField(required=False, min_value=1, allow_null=True, max_value=3650)
    includeBreakdown = serializers.BooleanField(required=False, default=True)

    def _validate_month(self, value, field_name):
        if not isinstance(value, str):
            raise serializers.ValidationError({field_name: "Must be a string in YYYY-MM format."})
        parts = value.split("-")
        if len(parts) != 2:
            raise serializers.ValidationError({field_name: "Must be in YYYY-MM format."})
        year, month = parts
        if len(year) != 4 or len(month) != 2 or not year.isdigit() or not month.isdigit():
            raise serializers.ValidationError({field_name: "Must be in YYYY-MM format."})
        month_int = int(month)
        if month_int < 1 or month_int > 12:
            raise serializers.ValidationError({field_name: "Month must be 01-12."})
        return value

    def _validate_person(self, person_id):
        request = self.context["request"]
        try:
            UUID(str(person_id))
        except (TypeError, ValueError):
            raise serializers.ValidationError({"personId": "Invalid UUID."})
        if not Person.objects.filter(id=person_id, owner=request.user).exists():
            raise serializers.ValidationError({"personId": "Must reference one of your people."})

    def validate(self, attrs):
        scope_type = attrs["scopeType"]
        payload = attrs["scopePayload"] if isinstance(attrs["scopePayload"], dict) else None
        if payload is None:
            raise serializers.ValidationError({"scopePayload": "Must be an object."})

        if scope_type == ShareScopeType.MONTH:
            month = payload.get("month")
            self._validate_month(month, "month")
        elif scope_type == ShareScopeType.RANGE:
            start = self._validate_month(payload.get("start"), "start")
            end = self._validate_month(payload.get("end"), "end")
            if start > end:
                raise serializers.ValidationError({"scopePayload": "start must be <= end."})
        elif scope_type == ShareScopeType.PERSON_MONTH:
            person_id = payload.get("personId")
            month = payload.get("month")
            if not person_id:
                raise serializers.ValidationError({"personId": "This field is required."})
            self._validate_person(person_id)
            self._validate_month(month, "month")
        elif scope_type == ShareScopeType.PERSON_RANGE:
            person_id = payload.get("personId")
            if not person_id:
                raise serializers.ValidationError({"personId": "This field is required."})
            self._validate_person(person_id)
            start = self._validate_month(payload.get("start"), "start")
            end = self._validate_month(payload.get("end"), "end")
            if start > end:
                raise serializers.ValidationError({"scopePayload": "start must be <= end."})
        else:
            raise serializers.ValidationError({"scopeType": "Unsupported scope type."})
        return attrs

    def create(self, validated_data):
        request = self.context["request"]
        expires_in_days = validated_data.get("expiresInDays")
        expires_at = None
        if expires_in_days:
            expires_at = timezone.now() + timedelta(days=expires_in_days)

        raw_token = generate_share_token()
        token_hash = hash_share_token(raw_token)

        share = PublicShareLink.objects.create(
            owner=request.user,
            token_hash=token_hash,
            scope_type=validated_data["scopeType"],
            scope_payload=validated_data["scopePayload"],
            permissions={"viewOnly": True, "includeBreakdown": validated_data.get("includeBreakdown", True)},
            expires_at=expires_at,
        )
        share._raw_token = raw_token
        return share


class PublicShareLinkUpdateSerializer(serializers.Serializer):
    expiresInDays = serializers.IntegerField(required=False, min_value=1, allow_null=True, max_value=3650)
    includeBreakdown = serializers.BooleanField(required=False)
