"""Запускать ЛОКАЛЬНО (не в проде): python deploy/make_session.py
Печатает StringSession один раз, положи его в .env БЕЗ кавычек."""
from telethon.sync import TelegramClient
from telethon.sessions import StringSession

api_id = int(input("api_id: "))
api_hash = input("api_hash: ")
with TelegramClient(StringSession(), api_id, api_hash) as c:
    print("\nTG_SESSION_STRING=" + c.session.save())
