import random

def generate_unique_sum(amount: int) -> int:
    """Добавляет случайное число от 1 до 99 к сумме, чтобы отличать платежи."""
    add = random.randint(1, 99)
    return amount + add

def format_datetime(dt):
    if dt:
        return dt.strftime("%d.%m.%Y %H:%M")
    return "—"
