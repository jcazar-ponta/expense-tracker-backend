from decimal import Decimal, ROUND_HALF_UP

from .month_utils import iter_months_inclusive, month_key

TWO_PLACES = Decimal("0.01")
ONE_HUNDRED = Decimal("100")


def round_to_two(value: Decimal) -> Decimal:
    return value.quantize(TWO_PLACES, rounding=ROUND_HALF_UP)


def _to_decimal(value) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def calculate_allocations(item):
    results = {}
    allocations = list(item.allocations.all())
    total_amount = _to_decimal(item.total_amount)

    if item.split_type == "EQUAL":
        active = [alloc for alloc in allocations if _to_decimal(alloc.value) > 0]
        if not active:
            return {}
        per_person = total_amount / Decimal(len(active))
        for alloc in active:
            results[str(alloc.person_id)] = round_to_two(per_person)
        diff = round_to_two(total_amount - sum(results.values(), Decimal("0")))
        if diff != 0:
            first_person_id = str(active[0].person_id)
            results[first_person_id] = round_to_two(results[first_person_id] + diff)
        return results

    if item.split_type == "CUSTOM_AMOUNT":
        for alloc in allocations:
            results[str(alloc.person_id)] = round_to_two(_to_decimal(alloc.value))
        return results

    if item.split_type == "PERCENT":
        for alloc in allocations:
            value = (total_amount * _to_decimal(alloc.value)) / ONE_HUNDRED
            results[str(alloc.person_id)] = round_to_two(value)
        diff = round_to_two(total_amount - sum(results.values(), Decimal("0")))
        if diff != 0 and allocations:
            first_person_id = str(allocations[0].person_id)
            results[first_person_id] = round_to_two(results[first_person_id] + diff)
        return results

    if item.split_type == "SHARES":
        total_shares = sum((_to_decimal(alloc.value) for alloc in allocations), Decimal("0"))
        if total_shares == 0:
            return {}
        for alloc in allocations:
            value = (total_amount * _to_decimal(alloc.value)) / total_shares
            results[str(alloc.person_id)] = round_to_two(value)
        diff = round_to_two(total_amount - sum(results.values(), Decimal("0")))
        if diff != 0 and allocations:
            first_person_id = str(allocations[0].person_id)
            results[first_person_id] = round_to_two(results[first_person_id] + diff)
        return results

    return {}


def generate_schedule(items):
    schedule = []
    for item in items:
        person_allocations = calculate_allocations(item)
        for person_id, total_responsibility in person_allocations.items():
            monthly_base = total_responsibility / Decimal(item.installment_months)
            accumulated = Decimal("0")
            for index, month in enumerate(iter_months_inclusive(item.start_month, item.start_month, item.installment_months)):
                if index == item.installment_months - 1:
                    principal_due = round_to_two(total_responsibility - accumulated)
                else:
                    principal_due = round_to_two(monthly_base)
                    accumulated = round_to_two(accumulated + principal_due)

                schedule.append(
                    {
                        "month": month,
                        "person_id": person_id,
                        "item_id": str(item.id),
                        "total_due": principal_due,
                    }
                )
    return schedule


def get_relevant_months(schedule, payments):
    months = {entry["month"] for entry in schedule}
    months.update(payment.month for payment in payments)
    months.add(month_key())
    return sorted(months)


def calculate_monthly_summary(person_id, target_month, schedule, payments, all_months):
    carryover_balance = Decimal("0")
    current_calendar_month = month_key()

    for month in all_months:
        due_this_month = sum(
            (entry["total_due"] for entry in schedule if entry["person_id"] == str(person_id) and entry["month"] == month),
            Decimal("0"),
        )
        paid_this_month = sum(
            (_to_decimal(payment.amount_paid) for payment in payments if str(payment.person_id) == str(person_id) and payment.month == month),
            Decimal("0"),
        )
        net_due = round_to_two(due_this_month + carryover_balance)

        if month == target_month:
            remaining = round_to_two(max(Decimal("0"), net_due - paid_this_month))
            credit = round_to_two(max(Decimal("0"), paid_this_month - net_due))
            return {
                "dueFromItems": float(round_to_two(due_this_month)),
                "carryoverFromPrevious": float(round_to_two(carryover_balance)),
                "totalPayable": float(round_to_two(net_due)),
                "paid": float(round_to_two(paid_this_month)),
                "remaining": float(remaining),
                "credit": float(credit),
            }

        if month < current_calendar_month:
            carryover_balance = round_to_two(net_due - paid_this_month)

    return {
        "dueFromItems": 0.0,
        "carryoverFromPrevious": 0.0,
        "totalPayable": 0.0,
        "paid": 0.0,
        "remaining": 0.0,
        "credit": 0.0,
    }
