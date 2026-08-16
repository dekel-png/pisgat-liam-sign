# -*- coding: utf-8 -*-
"""Telegram delivery — signed documents land in Dekel's ops chat."""
import os
import requests

API = "https://api.telegram.org/bot{tok}/{method}"


def _creds():
    return os.environ.get("TELEGRAM_BOT_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")


def send_message(text):
    tok, chat = _creds()
    if not tok or not chat:
        return False
    r = requests.post(API.format(tok=tok, method="sendMessage"),
                      data={"chat_id": chat, "text": text}, timeout=30)
    return r.ok and r.json().get("ok", False)


def send_document(filename, data, caption=None):
    tok, chat = _creds()
    if not tok or not chat:
        return False
    payload = {"chat_id": chat}
    if caption:
        payload["caption"] = caption[:1000]
    r = requests.post(API.format(tok=tok, method="sendDocument"),
                      data=payload,
                      files={"document": (filename, data, "application/octet-stream")},
                      timeout=120)
    return r.ok and r.json().get("ok", False)
