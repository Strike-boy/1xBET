import random
import re
from datetime import datetime, timedelta, timezone

# Часовой пояс Узбекистана (UTC+5)
UZ_TZ = timezone(timedelta(hours=5))

# Месяцы на узбекском языке
MONTHS_UZ = {
    1: 'Yanvar', 2: 'Fevral', 3: 'Mart', 4: 'Aprel',
    5: 'May', 6: 'Iyun', 7: 'Iyul', 8: 'Avgust',
    9: 'Sentabr', 10: 'Oktabr', 11: 'Noyabr', 12: 'Dekabr'
}


def generate_extra_amount() -> int:
    """Генерирует случайное число от 50 до 99 для идентификации платежа."""
    return random.randint(50, 99)


def format_number(number: int) -> str:
    """
    Форматирует число с пробелами для лучшей читаемости.
    
    Примеры:
        format_number(40000) -> "40 000"
        format_number(1000000) -> "1 000 000"
    """
    return f"{number:,}".replace(",", " ")


def format_date_uz(date_obj: datetime) -> str:
    """
    Форматирует дату на узбекском языке.
    
    Пример:
        format_date_uz(datetime(2026, 7, 10)) -> "10 Iyul 2026"
    """
    day = date_obj.day
    month = MONTHS_UZ[date_obj.month]
    year = date_obj.year
    return f"{day} {month} {year}"


def get_last_four_digits(card_number: str) -> str:
    """
    Извлекает последние 4 цифры из номера карты.
    
    Примеры:
        get_last_four_digits("1234 5678 9012 3456") -> "3456"
        get_last_four_digits("1234567890123456") -> "3456"
        get_last_four_digits("") -> "****"
    """
    if not card_number:
        return "****"
    
    # Удаляем пробелы и другие разделители
    clean = re.sub(r'[\s\-]', '', card_number)
    
    # Если строка пустая после очистки
    if not clean:
        return "****"
    
    # Если есть только последние 4 цифры или меньше
    if len(clean) <= 4:
        return clean.zfill(4)
    
    # Возвращаем последние 4 цифры
    return clean[-4:]


def get_status_emoji(status: str) -> str:
    """
    Возвращает эмодзи для статуса транзакции.
    
    Аргументы:
        status: 'checking', 'done', или 'cancelled'
    
    Возвращает:
        🟡 для checking
        ✅ для done
        ❌ для cancelled
        ❓ для неизвестного статуса
    """
    status_map = {
        'checking': '🟡',
        'done': '✅',
        'cancelled': '❌'
    }
    return status_map.get(status, '❓')


def get_type_emoji(order_type: str) -> str:
    """
    Возвращает эмодзи и название для типа операции.
    
    Аргументы:
        order_type: 'deposit' или 'withdraw'
    
    Возвращает:
        '💰 Balans to\'ldirish' для deposit
        '📤 Pul yechish' для withdraw
        '❓ Noma\'lum' для неизвестного типа
    """
    if order_type == 'deposit':
        return '💰 Balans to\'ldirish'
    elif order_type == 'withdraw':
        return '📤 Pul yechish'
    return '❓ Noma\'lum'


def format_amount(amount: int, order_type: str) -> str:
    """
    Форматирует сумму с знаком для отображения в истории.
    
    Аргументы:
        amount: сумма
        order_type: 'deposit' или 'withdraw'
    
    Возвращает:
        '+40 000' для пополнения
        '-25 000' для вывода
    """
    formatted = format_number(amount)
    if order_type == 'deposit':
        return f"+{formatted}"
    else:  # withdraw
        return f"-{formatted}"


def format_card_display(card_number: str, order_type: str) -> str:
    """
    Форматирует номер карты для отображения в истории.
    
    Аргументы:
        card_number: номер карты
        order_type: 'deposit' или 'withdraw'
    
    Возвращает:
        '💳 ** ** 1077' для пополнения
        '💳 **** 1077' для вывода
    """
    last_four = get_last_four_digits(card_number)
    
    if order_type == 'deposit':
        return f"💳 ** ** {last_four}"
    else:  # withdraw
        return f"💳 **** {last_four}"


def parse_datetime_with_tz(date_str: str, tz: timezone) -> datetime:
    """
    Парсит строку с датой и временем из БД и возвращает datetime с указанным часовым поясом.
    
    Аргументы:
        date_str: строка с датой и временем (ISO формат или '%Y-%m-%d %H:%M:%S')
        tz: часовой пояс (timezone объект)
    
    Возвращает:
        datetime с указанным часовым поясом
    """
    if not date_str:
        return datetime.now(tz)
    
    try:
        # Пытаемся распарсить ISO формат
        if 'T' in date_str:
            dt = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
        else:
            dt = datetime.strptime(date_str, '%Y-%m-%d %H:%M:%S')
        
        # ВАЖНО: Если datetime уже имеет часовой пояс, просто конвертируем
        if dt.tzinfo is not None:
            return dt.astimezone(tz)
        
        # Если datetime без часового пояса, добавляем указанный
        dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(tz)
        
    except (ValueError, TypeError):
        return datetime.now(tz)


def format_transaction_for_history(order: dict, tz: timezone) -> str:
    """
    Форматирует одну транзакцию для отображения в истории.
    
    Аргументы:
        order: словарь с данными транзакции из БД
        tz: часовой пояс (timezone объект)
    
    Возвращает:
        Отформатированная строка с транзакцией
    """
    # Извлекаем время с учетом часового пояса
    created_at = order.get('created_at', '')
    dt = parse_datetime_with_tz(created_at, tz)
    time_str = dt.strftime('%H:%M')
    
    # Статус и тип
    status_emoji = get_status_emoji(order.get('status', ''))
    type_name = get_type_emoji(order.get('order_type', ''))
    
    # Сумма
    amount = order.get('amount', 0) + order.get('extra_amount', 0)
    amount_str = format_amount(amount, order.get('order_type', 'deposit'))
    
    # Карта
    card_number = order.get('withdraw_card', '')
    if not card_number and order.get('order_type') == 'deposit':
        # Для пополнения используем card_used
        card_number = order.get('card_used', '')
    
    card_display = format_card_display(card_number, order.get('order_type', 'deposit'))
    
    return (
        f"{time_str}  {type_name}  {status_emoji}\n"
        f"💵 {amount_str}\n"
        f"{card_display}"
    )


def group_transactions_by_date(orders: list, tz: timezone) -> dict:
    """
    Группирует транзакции по датам с учетом часового пояса.
    
    Аргументы:
        orders: список транзакций
        tz: часовой пояс (timezone объект)
    
    Возвращает:
        Словарь {date_key: [список транзакций]}
    """
    grouped = {}
    for order in orders:
        created_at = order.get('created_at', '')
        dt = parse_datetime_with_tz(created_at, tz)
        date_key = dt.strftime('%Y-%m-%d')
        
        if date_key not in grouped:
            grouped[date_key] = []
        grouped[date_key].append(order)
    
    return grouped
