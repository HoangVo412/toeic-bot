# -*- coding: utf-8 -*-
"""
Test gui tin Telegram. Chi lam 3 viec:
  1. Hoi Telegram xem token co hop le khong (getMe)
  2. Gui mot tin nhan thuong
  3. Gui mot tin co NUT BAM, va sua chinh tin do sau 3 giay
     -> xac nhan co che editMessageText hoat dong, day la nen tang cua man on tap
"""
import os
import sys
import json
import time

API = "https://api.telegram.org/bot%s/%s"


def die(ly_do, huong_xu_ly=""):
    print("")
    print("=" * 62)
    print("THAT BAI: " + ly_do)
    if huong_xu_ly:
        print("HUONG XU LY: " + huong_xu_ly)
    print("=" * 62)
    sys.exit(1)


def goi(token, phuong_thuc, du_lieu=None):
    import requests
    r = requests.post(API % (token, phuong_thuc), json=du_lieu or {}, timeout=20)
    try:
        kq = r.json()
    except Exception:
        die("Telegram tra ve khong phai JSON (HTTP %d)." % r.status_code)
    if not kq.get("ok"):
        mo_ta = kq.get("description", "(khong ro)")
        ma = kq.get("error_code")
        goi_y = ""
        if ma == 401:
            goi_y = "Token sai. Lay lai token tu BotFather."
        elif "chat not found" in mo_ta.lower():
            goi_y = ("Chua bam Start cho bot, HOAC chat_id sai. "
                     "Mo bot tren Telegram, bam Start, nhan mot tin, roi chay lai.")
        elif "bot was blocked" in mo_ta.lower():
            goi_y = "Bot dang bi chan. Mo bot tren Telegram va bo chan."
        die("Telegram tu choi '%s': %s (ma %s)" % (phuong_thuc, mo_ta, ma), goi_y)
    return kq["result"]


def main():
    token = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

    print("=" * 62)
    print("CAU HINH DANG DUNG")
    print("=" * 62)
    print("TELEGRAM_TOKEN   : " + ("co, %d ky tu" % len(token) if token else "(TRONG)"))
    print("TELEGRAM_CHAT_ID : " + (chat_id if chat_id else "(TRONG)"))
    print("")

    if not token:
        die("Bien TELEGRAM_TOKEN chua toi duoc script.",
            "Tao secret TELEGRAM_TOKEN trong repo.")
    if not chat_id:
        die("Bien TELEGRAM_CHAT_ID chua toi duoc script.",
            "Tao secret TELEGRAM_CHAT_ID trong repo.")

    # --- 1. Kiem tra token ---
    me = goi(token, "getMe")
    print("[1/4] Token hop le. Bot: @%s  (%s)" % (me.get("username"), me.get("first_name")))

    # --- 2. Gui tin thuong ---
    goi(token, "sendMessage", {
        "chat_id": chat_id,
        "text": "Ket noi thanh cong.\nBot TOEIC da san sang.",
    })
    print("[2/4] Gui tin nhan thuong: OK")

    # --- 3. Gui tin co nut bam ---
    tin = goi(token, "sendMessage", {
        "chat_id": chat_id,
        "parse_mode": "HTML",
        "text": ("<b>THU MAN ON TAP</b>\n\n"
                 "<b>advantage</b>\n"
                 "<code>/ədˈvæn.tɪdʒ/</code>\n\n"
                 "Their early entry gave them a clear ______ over competitors.\n\n"
                 "<i>Tin nhan nay se tu doi noi dung sau 3 giay...</i>"),
        "reply_markup": {"inline_keyboard": [[
            {"text": "Xem nghia", "callback_data": "demo_xem"},
            {"text": "Nghe", "callback_data": "demo_nghe"},
        ]]},
    })
    message_id = tin["message_id"]
    print("[3/4] Gui tin co nut bam: OK  (message_id = %d)" % message_id)

    # --- 4. Sua chinh tin do ---
    time.sleep(3)
    goi(token, "editMessageText", {
        "chat_id": chat_id,
        "message_id": message_id,
        "parse_mode": "HTML",
        "text": ("<b>THU MAN ON TAP</b>\n\n"
                 "<b>advantage</b>\n"
                 "<code>/ədˈvæn.tɪdʒ/</code>\n"
                 "loi the\n\n"
                 "Their early entry gave them a clear <b>advantage</b> over competitors.\n"
                 "→ Viec gia nhap som mang lai cho ho loi the ro rang so voi doi thu.\n\n"
                 "<i>Noi dung da doi tai cho, khong co tin nhan moi.</i>"),
        "reply_markup": {"inline_keyboard": [[
            {"text": "Nho", "callback_data": "demo_nho"},
            {"text": "Quen", "callback_data": "demo_quen"},
            {"text": "De sau", "callback_data": "demo_hoan"},
        ]]},
    })
    print("[4/4] Sua noi dung tin nhan tai cho: OK")

    print("")
    print("=" * 62)
    print("THANH CONG.")
    print("Mo Telegram kiem tra:")
    print("  - Co 2 tin nhan moi")
    print("  - Tin thu hai da TU DOI noi dung, khong sinh tin thu ba")
    print("  - Tin thu hai co 3 nut: Nho / Quen / De sau")
    print("Bam thu cac nut: chua co gi xay ra, vi chua dung Worker nhan phan hoi.")
    print("=" * 62)


if __name__ == "__main__":
    main()
