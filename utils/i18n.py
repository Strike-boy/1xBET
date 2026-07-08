import json
import os
from typing import Dict

translations = {}
locales_dir = os.path.join(os.path.dirname(__file__), '..', 'locales')

def load_translations():
    for lang in ['ru', 'uz']:
        path = os.path.join(locales_dir, f'{lang}.json')
        if os.path.exists(path):
            with open(path, 'r', encoding='utf-8') as f:
                translations[lang] = json.load(f)

load_translations()

def get_text(key: str, lang: str = 'ru', **kwargs) -> str:
    text = translations.get(lang, {}).get(key, translations.get('ru', {}).get(key, key))
    if kwargs:
        text = text.format(**kwargs)
    return text
