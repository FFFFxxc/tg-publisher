"""Runtime controls for the two network-channel workflows and their account bindings."""
from __future__ import annotations

import json
import asyncio
import re
from urllib.parse import urlsplit

from .logic import canonical_ref, parse_ref, parse_times, u16

IDS = ('weekly', 'promo')
REACTION_SECONDS = 6 * 60 * 60


def defaults(cfg, network_id):
    if network_id not in IDS:
        raise LookupError('Сеточный канал не найден')
    common = {'enabled': True}
    if network_id == 'weekly':
        return {**common, 'source_ref': getattr(cfg, 'destination', ''), 'target_ref': '@comics_komixy',
                'lookback_hours': 168, 'times': ['12:00', '16:00', '20:00'], 'min_posts': 1, 'max_posts': 3,
                'caption_text': 'Весь наш контент', 'caption_url': 'https://t.me/comics_komixy/29',
                'emoji_id': '5462931610028510371'}
    return {**common, 'source_ref': '@anime_edit_videoo', 'target_ref': getattr(cfg, 'destination', ''),
            'lookback_hours': 48, 'times': ['14:00', '20:00']}


async def load_settings(db, cfg, network_id):
    result = defaults(cfg, network_id)
    raw = await db.kv_get('network:' + network_id)
    if isinstance(raw, str) and raw:
        saved = json.loads(raw)
        if isinstance(saved, dict):
            result.update({k: v for k, v in saved.items() if k in result})
    return result


def reaction_target(network_id, settings):
    return settings['target_ref'] if network_id == 'weekly' else settings['source_ref']


def validate_settings(cfg, network_id, current, body):
    if not isinstance(body, dict):
        raise ValueError('Ожидается объект настроек')
    allowed = set(defaults(cfg, network_id)) | {'account_ids'}
    if set(body) - allowed:
        raise ValueError('Неизвестные поля: ' + ', '.join(sorted(set(body) - allowed)))
    result = {**current, **{k: v for k, v in body.items() if k != 'account_ids'}}
    if not isinstance(result['enabled'], bool):
        raise ValueError('enabled должен быть boolean')
    for field in ('source_ref', 'target_ref'):
        ref = result[field]
        if not isinstance(ref, str) or not ref.strip() or len(ref) > 200:
            raise ValueError(f'{field}: укажите Telegram-канал или ссылку приглашения')
        kind, value = parse_ref(ref.strip())
        if kind == 'username' and not re.fullmatch(r'[A-Za-z0-9_]{4,32}', str(value)):
            raise ValueError(f'{field}: неверный Telegram username')
        if kind == 'id' and (not value or not -(2**63) < value < 2**63):
            raise ValueError(f'{field}: неверный Telegram ID')
        result[field] = canonical_ref(ref.strip())
    if result['source_ref'] == result['target_ref']:
        raise ValueError('Источник и канал назначения должны различаться')
    hours = result['lookback_hours']
    if isinstance(hours, bool) or not isinstance(hours, int) or not 1 <= hours <= 720:
        raise ValueError('Период отбора: целое число от 1 до 720 часов')
    times = result['times']
    if not isinstance(times, list) or not 1 <= len(times) <= 12 or not all(isinstance(t, str) and re.fullmatch(r'\d{2}:\d{2}', t) for t in times):
        raise ValueError('Укажите 1–12 времён HH:mm')
    parsed = parse_times(','.join(times))
    if len(set(times)) != len(times):
        raise ValueError('Время публикаций не должно повторяться')
    result['times'] = [t.strftime('%H:%M') for t in parsed]
    if network_id == 'weekly':
        lo, hi = result['min_posts'], result['max_posts']
        if any(isinstance(n, bool) or not isinstance(n, int) for n in (lo, hi)) or not 1 <= lo <= hi <= 3 or hi > len(times):
            raise ValueError('Квота: 1–3 поста, минимум ≤ максимум; времён должно хватать')
        text = result['caption_text']
        if not isinstance(text, str) or not text.strip() or u16(text) > 500:
            raise ValueError('Текст подписи: 1–500 символов UTF-16')
        result['caption_text'] = text.strip()
        url = result['caption_url']
        if not isinstance(url, str) or len(url) > 1000 or urlsplit(url).scheme != 'https' or not urlsplit(url).netloc:
            raise ValueError('Ссылка подписи должна начинаться с https://')
        emoji = result['emoji_id']
        if not isinstance(emoji, str) or not re.fullmatch(r'\d{1,19}', emoji) or not 0 < int(emoji) < 2**63:
            raise ValueError('ID кастомного эмодзи: строка с положительным 64-битным числом')
    accounts = body.get('account_ids')
    if accounts is not None:
        if not isinstance(accounts, list) or len(accounts) > 100 or not all(isinstance(a, str) and re.fullmatch(r'[a-f0-9]{32}', a) for a in accounts) or len(set(accounts)) != len(accounts):
            raise ValueError('Укажите список уникальных ID подключённых аккаунтов')
    return result, accounts


class NetworkService:
    def __init__(self, cfg, db, lock=None):
        self.cfg, self.db = cfg, db
        self.lock = lock or asyncio.Lock()

    async def list(self):
        accounts = [{k: v for k, v in row.items() if k != 'session_path'} for row in await self.db.activity_accounts()]
        items = []
        for network_id in IDS:
            settings = await load_settings(self.db, self.cfg, network_id)
            bindings = await self.db.network_bindings(network_id)
            items.append({'id': network_id, 'label': 'Лучшие посты → дополнительный канал' if network_id == 'weekly' else 'Реклама сеточного канала',
                          **settings, 'account_ids': [r['account_id'] for r in bindings if r['enabled']],
                          'bindings': bindings, 'recent_runs': await self.db.network_recent(network_id)})
        return {'items': items, 'accounts': accounts, 'reaction_interval_hours': 6}

    async def update(self, network_id, body):
        async with self.lock:
            return await self._update(network_id, body)

    async def _update(self, network_id, body):
        current = await load_settings(self.db, self.cfg, network_id)
        settings, accounts = validate_settings(self.cfg, network_id, current, body)
        if accounts is not None:
            valid = {row['id'] for row in await self.db.activity_accounts()}
            if set(accounts) - valid:
                raise ValueError('Один из аккаунтов уже удалён: обновите страницу')
        await self.db.save_network_settings(network_id, settings, accounts,
                                            reaction_target(network_id, current) != reaction_target(network_id, settings))
        item = next(row for row in (await self.list())['items'] if row['id'] == network_id)
        return {'ok': True, 'item': item, 'reaction_interval_hours': 6}
