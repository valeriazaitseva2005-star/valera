"""
Сповіщення в Telegram про нові листи у пошті STU (@stuba.sk).

Скрипт заходить у скриньку через IMAP, знаходить непрочитані листи,
про які ще не повідомляв, і надсилає в Telegram відправника й тему.
Листи НЕ позначаються прочитаними: скрипт лише ставить на них
невидиму позначку "TgNotified", щоб не повідомляти двічі.

Потрібні змінні середовища:
  STU_LOGIN     - AIS-логін (без @stuba.sk)
  STU_PASSWORD  - пароль від AIS
  TG_TOKEN      - токен бота від @BotFather
  TG_CHAT_ID    - твій chat id у Telegram
  RUN_ONCE=1    - (необов'язково) перевірити один раз і завершити
"""

import email
import html
import imaplib
import os
import re
import time
import urllib.parse
import urllib.request
from email.header import decode_header, make_header

IMAP_HOST = "imap.stuba.sk"
IMAP_PORT = 993
FLAG = "TgNotified"
CHECK_EVERY_SECONDS = 60
MAX_BODY_CHARS = 3000  # Telegram дозволяє до 4096 символів в одному повідомленні

USER = os.environ["STU_LOGIN"]
PASSWORD = os.environ["STU_PASSWORD"]
TG_TOKEN = os.environ["TG_TOKEN"]
TG_CHAT_ID = os.environ["TG_CHAT_ID"]


def decode(value):
    """Розкодовує заголовки на кшталт =?UTF-8?B?...?= у звичайний текст."""
    try:
        return str(make_header(decode_header(value or "")))
    except Exception:
        return value or ""


def html_to_text(raw_html):
    """Дуже простий перетворювач HTML у текст."""
    text = re.sub(r"(?is)<(script|style).*?</\1>", "", raw_html)
    text = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</li>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)
    return html.unescape(text)


def get_body_and_attachments(msg):
    """Повертає (текст листа, список назв вкладень)."""
    plain, html_part, attachments = None, None, []

    for part in msg.walk():
        if part.is_multipart():
            continue
        filename = part.get_filename()
        if filename or part.get_content_disposition() == "attachment":
            attachments.append(decode(filename) or "без назви")
            continue

        payload = part.get_payload(decode=True)
        if payload is None:
            continue
        charset = part.get_content_charset() or "utf-8"
        text = payload.decode(charset, errors="replace")

        if part.get_content_type() == "text/plain" and plain is None:
            plain = text
        elif part.get_content_type() == "text/html" and html_part is None:
            html_part = text

    body = plain if plain else html_to_text(html_part or "")
    body = re.sub(r"\n\s*\n\s*\n+", "\n\n", body).strip()  # прибрати зайві порожні рядки

    if len(body) > MAX_BODY_CHARS:
        body = body[:MAX_BODY_CHARS] + "\n\n… (лист обрізано, повна версія у пошті)"
    return body or "(порожній лист)", attachments


def send_telegram(text):
    url = f"https://api.telegram.org/bot{TG_TOKEN}/sendMessage"
    data = urllib.parse.urlencode({"chat_id": TG_CHAT_ID, "text": text}).encode()
    urllib.request.urlopen(url, data=data, timeout=20)


def check_mail():
    mail = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT)
    mail.login(USER, PASSWORD)
    mail.select("INBOX")

    # Непрочитані листи, про які ще не надсилали сповіщення
    _, data = mail.uid("search", None, "UNSEEN", "UNKEYWORD", FLAG)
    uids = data[0].split()

    for uid in uids:
        # BODY.PEEK читає лист, не позначаючи його прочитаним
        _, msg_data = mail.uid("fetch", uid, "(BODY.PEEK[])")
        msg = email.message_from_bytes(msg_data[0][1])
        sender = decode(msg.get("From"))
        subject = decode(msg.get("Subject")) or "(без теми)"
        body, attachments = get_body_and_attachments(msg)

        text = f"📬 Новий лист STU\n\nВід: {sender}\nТема: {subject}\n\n{body}"
        if attachments:
            text += "\n\n📎 Вкладення: " + ", ".join(attachments)
        send_telegram(text)
        mail.uid("store", uid, "+FLAGS", f"({FLAG})")

    mail.logout()
    return len(uids)


def main():
    if os.environ.get("RUN_ONCE") == "1":
        print(f"Нових листів: {check_mail()}")
        return

    print("Стежу за поштою... (Ctrl+C щоб зупинити)")
    while True:
        try:
            count = check_mail()
            if count:
                print(f"Надіслано сповіщень: {count}")
        except Exception as e:
            print(f"Помилка: {e}")
        time.sleep(CHECK_EVERY_SECONDS)


if __name__ == "__main__":
    main()
