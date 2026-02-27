from datetime import datetime


def month_key(dt=None):
    target = dt or datetime.utcnow()
    return target.strftime("%Y-%m")


def add_months(month_str: str, offset: int) -> str:
    year, month = map(int, month_str.split("-"))
    index = (year * 12 + (month - 1)) + offset
    next_year = index // 12
    next_month = index % 12 + 1
    return f"{next_year:04d}-{next_month:02d}"


def iter_months_inclusive(start_month: str, end_month: str, fixed_count: int | None = None):
    if fixed_count is not None:
        for offset in range(fixed_count):
            yield add_months(start_month, offset)
        return

    cursor = start_month
    while cursor <= end_month:
        yield cursor
        cursor = add_months(cursor, 1)
