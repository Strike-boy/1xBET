import random

def generate_extra_amount() -> int:
    """Генерирует случайное число от 50 до 99 для идентификации платежа."""
    return random.randint(50, 99)
