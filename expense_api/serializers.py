from django.db import transaction
from django.utils import timezone
from rest_framework import serializers

from .models import ActionType, Allocation, AppSettings, EntityType, ItemExpense, LedgerEvent, Payment, Person
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
