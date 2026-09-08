# -*- coding: utf-8 -*-
"""
Chuyen ma toan bo file phat am sang OGG/Opus, upload len Telegram de lay
file_id, roi luu file_id vao cot Y cua tab TuVung.

VI SAO PHAI LAM:
  Telegram chi dung "voice message" (cham la nghe ngay, khong tai) khi file la
  OGG ma hoa bang OPUS. Merriam-Webster chi co MP3 va OGG/Vorbis - ca hai deu
  bi ha xuong thanh Audio hoac Document.
  Cloudflare Worker khong chuyen ma duoc. Nen phai chuyen ma san mot lan o day,
  gui len Telegram de lay file_id, sau do Worker chi viec gui bang file_id:
  dung dinh dang, tuc thi, khong phu thuoc Merriam-Webster con song hay khong.

CACH LAY file_id: bat buoc phai GUI file di that. Script gui roi XOA NGAY,
nen chat se nhap nhay mot luc roi sach. file_id van dung duoc sau khi xoa.

Chay duoc NHIEU LAN, tu bo qua nhung dong da co file_id.
GHI DAN sau moi lo nho, de lo chay dut giua chung thi khong mat cong da lam.
"""
import os
import sys
import json
import time
import subprocess

COT_WORD = 2       # B
COT_AUDIO = 7      # G
COT_FILE_ID = 25   # Y
TRONG = "-"
GHI_MOI = 40       # ghi vao Sheet sau moi bao nhieu dong lam duoc


def log(*a):
    print(*a)
    sys.stdout.flush()


def die(ly_do, huong_xu_ly=""):
    log("")
    log("=" * 62)
    log("THAT BAI: " + ly_do)
    if huong_xu_ly:
        log("HUONG XU LY: " + huong_xu_ly)
    log("=" * 62)
    sys.exit(1)


def chuyen_opus(du_lieu):
    """MP3 bytes -> OGG/Opus bytes. Tra None neu that bai."""
    try:
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k",
             "-ar", "48000", "-ac", "1", "-f", "ogg", "pipe:1"],
            input=du_lieu, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=40)
    except Exception as e:
        return None, "ffmpeg loi: " + type(e).__name__
    if p.returncode != 0 or not p.stdout:
        return None, "ffmpeg: " + p.stderr.decode("utf-8", "ignore")[:80]
    if p.stdout[:4] != b"OggS" or b"OpusHead" not in p.stdout[:200]:
        return None, "ket qua khong phai OGG/Opus"
    return p.stdout, ""


def main():
    sa_raw = os.environ.get("GOOGLE_SA_JSON", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    token = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()

    def so(ten, mac_dinh):
        try:
            return float(os.environ.get(ten) or mac_dinh)
        except ValueError:
            return float(mac_dinh)

    lo = int(so("BATCH_SIZE", 250))
    nghi = so("DELAY", 1.2)
    giu_lai = (os.environ.get("GIU_TIN") or "").strip().lower() in ("1", "true", "yes")

    log("=" * 62)
    log("CAU HINH DANG DUNG")
    log("=" * 62)
    log("SHEET_ID         : " + (sheet_id or "(TRONG)"))
    log("GOOGLE_SA_JSON   : " + ("co, %d ky tu" % len(sa_raw) if sa_raw else "(TRONG)"))
    log("TELEGRAM_TOKEN   : " + ("co, %d ky tu" % len(token) if token else "(TRONG)"))
    log("TELEGRAM_CHAT_ID : " + (chat_id or "(TRONG)"))
    log("BATCH_SIZE       : %d" % lo)
    log("DELAY            : %.1f giay giua hai file" % nghi)
    log("GIU_TIN          : " + ("BAT - khong xoa tin, de kiem tra bang mat"
                                 if giu_lai else "tat - gui xong xoa ngay"))
    log("Uoc tinh         : %.0f phut cho lo nay" % (lo * (nghi + 0.8) / 60))
    log("")

    for ten, gt in (("SHEET_ID", sheet_id), ("GOOGLE_SA_JSON", sa_raw),
                    ("TELEGRAM_TOKEN", token), ("TELEGRAM_CHAT_ID", chat_id)):
        if not gt:
            die("Bien %s chua toi duoc script." % ten)
    try:
        sa = json.loads(sa_raw)
    except Exception as e:
        die("GOOGLE_SA_JSON khong phai JSON hop le (%s)." % e)

    # --- ffmpeg ---
    try:
        v = subprocess.run(["ffmpeg", "-version"], stdout=subprocess.PIPE,
                           stderr=subprocess.STDOUT, timeout=20)
        log("ffmpeg: " + v.stdout.decode("utf-8", "ignore").split("\n")[0])
    except Exception:
        die("Khong tim thay ffmpeg.", "Kiem tra buoc cai ffmpeg trong workflow.")

    import requests
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    try:
        gc = gspread.authorize(Credentials.from_service_account_info(sa, scopes=scopes))
        ws = gc.open_by_key(sheet_id).worksheet("TuVung")
    except Exception as e:
        die("Khong mo duoc tab TuVung: %s" % e)

    tieu_de = ws.row_values(1)
    if len(tieu_de) < COT_FILE_ID or tieu_de[COT_FILE_ID - 1].strip() != "FileID":
        die("O Y1 chua co tieu de 'FileID'.", "Go chinh xac  FileID  vao o Y1.")

    tat_ca = ws.get_all_values()
    can_lam, da_co, khong_audio = [], 0, 0
    for i, hang in enumerate(tat_ca[1:], start=2):
        def o(c):
            return hang[c - 1].strip() if len(hang) >= c else ""
        audio, fid, word = o(COT_AUDIO), o(COT_FILE_ID), o(COT_WORD)
        if not word:
            continue
        if not audio or audio == TRONG:
            khong_audio += 1
            continue
        if fid:
            da_co += 1
            continue
        can_lam.append((i, word, audio))

    log("")
    log("Da co file_id      : %d" % da_co)
    log("Khong co phat am   : %d" % khong_audio)
    log("Can xu ly          : %d" % len(can_lam))
    if not can_lam:
        log("\nKhong con gi de lam.")
        return

    dot = can_lam[:lo]
    log("Lo nay xu ly       : %d file" % len(dot))
    log("")

    tg = "https://api.telegram.org/bot%s/" % token
    s = requests.Session()
    ket_qua = {}
    tk = {"ok": 0, "tai_hong": 0, "ffmpeg_hong": 0, "tele_hong": 0}
    ly_do = {}
    bat_dau = time.time()

    def ghi_vao_sheet():
        if not ket_qua:
            return
        ds = sorted(ket_qua)
        khoi, a, b = [], ds[0], ds[0]
        for d in ds[1:]:
            if d == b + 1:
                b = d
            else:
                khoi.append((a, b))
                a = b = d
        khoi.append((a, b))
        yc = [{"range": "Y%d:Y%d" % (x, y),
               "values": [[ket_qua[d]] for d in range(x, y + 1)]} for x, y in khoi]
        try:
            ws.batch_update(yc, value_input_option="RAW")
        except Exception as e:
            log("   CANH BAO: ghi Sheet that bai (%s). Se thu lai o lo sau." % e)
            return
        ket_qua.clear()

    for thu_tu, (dong, word, url) in enumerate(dot, start=1):
        # 1. tai
        try:
            r = s.get(url, timeout=25)
            if r.status_code != 200 or not r.content:
                tk["tai_hong"] += 1
                ly_do["tai HTTP %d" % r.status_code] = ly_do.get(
                    "tai HTTP %d" % r.status_code, 0) + 1
                continue
        except Exception as e:
            tk["tai_hong"] += 1
            ly_do["tai: " + type(e).__name__] = ly_do.get("tai: " + type(e).__name__, 0) + 1
            continue

        # 2. chuyen ma
        opus, loi = chuyen_opus(r.content)
        if not opus:
            tk["ffmpeg_hong"] += 1
            ly_do[loi[:40]] = ly_do.get(loi[:40], 0) + 1
            continue

        # 3. gui de lay file_id
        try:
            rr = s.post(tg + "sendVoice",
                        data={"chat_id": chat_id, "disable_notification": "true"},
                        files={"voice": ("%s.ogg" % word.replace(" ", "_"), opus,
                                         "audio/ogg")},
                        timeout=60)
            kq = rr.json()
        except Exception as e:
            tk["tele_hong"] += 1
            ly_do["gui: " + type(e).__name__] = ly_do.get("gui: " + type(e).__name__, 0) + 1
            continue
        if not kq.get("ok"):
            mo_ta = kq.get("description", "")[:50]
            tk["tele_hong"] += 1
            ly_do["Telegram: " + mo_ta] = ly_do.get("Telegram: " + mo_ta, 0) + 1
            if "Too Many Requests" in mo_ta or kq.get("error_code") == 429:
                cho = (kq.get("parameters") or {}).get("retry_after", 30)
                log("   Bi giu nhip, cho %d giay..." % cho)
                time.sleep(cho + 1)
            continue

        kq_r = kq["result"]
        fid = ((kq_r.get("voice") or {}).get("file_id")
               or (kq_r.get("audio") or {}).get("file_id")
               or (kq_r.get("document") or {}).get("file_id"))
        if not fid:
            tk["tele_hong"] += 1
            ly_do["khong lay duoc file_id"] = ly_do.get("khong lay duoc file_id", 0) + 1
        else:
            ket_qua[dong] = fid
            tk["ok"] += 1
            if tk["ok"] <= 3:
                log("   mau: %-16s -> %s" % (word, fid[:44] + "..."))

        # 4. xoa tin vua gui - file_id van dung duoc sau khi xoa
        if not giu_lai:
            try:
                s.post(tg + "deleteMessage",
                       json={"chat_id": chat_id, "message_id": kq_r["message_id"]},
                       timeout=20)
            except Exception:
                pass

        if len(ket_qua) >= GHI_MOI:
            ghi_vao_sheet()
        if thu_tu % 50 == 0:
            log("  ... %d/%d  |  lay duoc %d  |  %.1f phut"
                % (thu_tu, len(dot), tk["ok"], (time.time() - bat_dau) / 60))
        time.sleep(nghi)

    ghi_vao_sheet()

    log("")
    log("=" * 62)
    log("KET QUA LAN CHAY NAY  (%.1f phut)" % ((time.time() - bat_dau) / 60))
    log("=" * 62)
    log("Lay duoc file_id   : %d" % tk["ok"])
    log("Tai file hong      : %d" % tk["tai_hong"])
    log("Chuyen ma hong     : %d" % tk["ffmpeg_hong"])
    log("Telegram tu choi   : %d" % tk["tele_hong"])
    if ly_do:
        log("")
        log("Chi tiet:")
        for k, v in sorted(ly_do.items(), key=lambda x: -x[1])[:8]:
            log("   %-44s %d lan" % (k, v))
    con = len(can_lam) - len(dot)
    log("")
    if con > 0:
        log(">> Con %d file. Chay lai workflow nay." % con)
    else:
        log(">> Da xong toan bo.")
    log("=" * 62)


if __name__ == "__main__":
    main()
