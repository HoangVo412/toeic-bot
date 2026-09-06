# -*- coding: utf-8 -*-
"""
Nap phien am (IPA) va link audio phat am cho tung tu, lay tu Free Dictionary API.

NGUYEN TAC: KHONG ghi de cot IPA goc (cot D).
  - Ghi link audio vao cot G  (AudioURL)
  - Ghi IPA lay tu API vao cot W (IPA_API) de doi chieu
Sau khi co du lieu ca hai cot moi quyet dinh dung cot nao.

Script chay duoc NHIEU LAN: moi lan xu ly mot lo, tu bo qua nhung dong da xong.
Dong da xu ly nhung API khong co du lieu se duoc danh dau '-' de khong tra lai.
"""
import os
import sys
import json
import time
import unicodedata
from urllib.parse import quote

API = "https://api.dictionaryapi.dev/api/v2/entries/en/"
COT_WORD = 2      # B
COT_IPA_GOC = 4   # D
COT_AUDIO = 7     # G
COT_IPA_API = 23  # W
TRONG = "-"       # danh dau: da tra roi, khong co du lieu


def die(ly_do, huong_xu_ly=""):
    print("")
    print("=" * 60)
    print("THAT BAI: " + ly_do)
    if huong_xu_ly:
        print("HUONG XU LY: " + huong_xu_ly)
    print("=" * 60)
    sys.exit(1)


def bo_dau(s):
    """entree <- entrée : thu lai khi API tra 404."""
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def chon_du_lieu(entries):
    """
    Tra ve (ipa, audio_url).
    Uu tien giong My (-us). Neu khong co thi lay ban ghi dau tien co du lieu.
    """
    ipa_us = audio_us = None
    ipa_bat_ky = audio_bat_ky = None

    for e in entries:
        if not isinstance(e, dict):
            continue
        if not ipa_bat_ky and e.get("phonetic"):
            ipa_bat_ky = e["phonetic"]
        for ph in e.get("phonetics", []) or []:
            text = (ph.get("text") or "").strip()
            audio = (ph.get("audio") or "").strip()
            if audio.startswith("//"):
                audio = "https:" + audio
            la_us = "-us." in audio or "_us_" in audio or "-us&" in audio
            if la_us:
                if text and not ipa_us:
                    ipa_us = text
                if audio and not audio_us:
                    audio_us = audio
            if text and not ipa_bat_ky:
                ipa_bat_ky = text
            if audio and not audio_bat_ky:
                audio_bat_ky = audio

    ipa = ipa_us or ipa_bat_ky or ""
    audio = audio_us or audio_bat_ky or ""
    if ipa and not ipa.startswith("/"):
        ipa = "/" + ipa.strip("/") + "/"
    return ipa, audio


def tra_cuu(session, word):
    """Tra ve (ipa, audio, ma_trang_thai). ipa/audio co the la chuoi rong."""
    for ung_vien in (word, bo_dau(word)):
        try:
            r = session.get(API + quote(ung_vien), timeout=15)
        except Exception as e:
            return "", "", "LOI_MANG:%s" % type(e).__name__
        if r.status_code == 200:
            try:
                return chon_du_lieu(r.json()) + ("200",)
            except Exception:
                return "", "", "JSON_HONG"
        if r.status_code == 404:
            if ung_vien != word:
                return "", "", "404"
            continue          # thu tiep ban bo dau
        if r.status_code == 429:
            return "", "", "429"
        return "", "", str(r.status_code)
    return "", "", "404"


def main():
    sa_raw = os.environ.get("GOOGLE_SA_JSON", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    try:
        lo = int(os.environ.get("BATCH_SIZE") or 350)
    except ValueError:
        lo = 350
    try:
        nghi = float(os.environ.get("DELAY") or 0.25)
    except ValueError:
        nghi = 0.25

    print("=" * 60)
    print("CAU HINH DANG DUNG")
    print("=" * 60)
    print("SHEET_ID       : " + (sheet_id or "(TRONG)"))
    print("GOOGLE_SA_JSON : " + ("co, %d ky tu" % len(sa_raw) if sa_raw else "(TRONG)"))
    print("BATCH_SIZE     : %d tu moi lan chay" % lo)
    print("DELAY          : %.2f giay giua hai lan goi" % nghi)
    print("")

    if not sheet_id:
        die("Bien SHEET_ID chua toi duoc script.", "Kiem tra tab Variables cua repo.")
    if not sa_raw:
        die("Bien GOOGLE_SA_JSON chua toi duoc script.", "Kiem tra tab Secrets cua repo.")

    try:
        sa = json.loads(sa_raw)
    except Exception as e:
        die("GOOGLE_SA_JSON khong phai JSON hop le (%s)." % e, "Dan lai nguyen van file .json.")

    import requests
    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    try:
        gc = gspread.authorize(Credentials.from_service_account_info(sa, scopes=scopes))
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet("TuVung")
    except Exception as e:
        die("Khong mo duoc tab TuVung: %s" % e,
            "Chay lai workflow 'Test ket noi Google Sheets' de khoanh vung loi.")

    # --- Kiem tra tieu de cot W ---
    tieu_de = ws.row_values(1)
    if len(tieu_de) < COT_IPA_API or tieu_de[COT_IPA_API - 1].strip() != "IPA_API":
        die("O W1 chua co tieu de 'IPA_API'.",
            "Mo tab TuVung, go chinh xac  IPA_API  vao o W1 roi chay lai.")

    tat_ca = ws.get_all_values()
    tong = len(tat_ca) - 1
    print("Tab TuVung co %d dong du lieu." % tong)

    # --- Tim cac dong chua xu ly ---
    can_lam = []
    da_xong = 0
    for i, row in enumerate(tat_ca[1:], start=2):
        def o(idx):
            return row[idx - 1].strip() if len(row) >= idx else ""
        if o(COT_IPA_API):
            da_xong += 1
            continue
        word = o(COT_WORD)
        if word:
            can_lam.append((i, word))

    print("Da xu ly truoc do : %d" % da_xong)
    print("Con lai           : %d" % len(can_lam))
    if not can_lam:
        print("")
        print("Khong con gi de lam. Toan bo 1000 tu da duoc tra cuu.")
        return

    dot = can_lam[:lo]
    print("Lan chay nay xu ly: %d tu (dong %d -> %d)"
          % (len(dot), dot[0][0], dot[-1][0]))
    print("")

    session = requests.Session()
    session.headers.update({"User-Agent": "toeic-bot/1.0"})

    ket_qua = {}
    thong_ke = {"co_ca_hai": 0, "chi_ipa": 0, "chi_audio": 0, "khong_co": 0}
    loi_khac = {}
    vi_du = []

    for thu_tu, (dong, word) in enumerate(dot, start=1):
        ipa, audio, ma = tra_cuu(session, word)

        if ma == "429":
            print("")
            print("BI CHAN TAM THOI (429) sau %d tu. Dung lai va ghi phan da lam." % (thu_tu - 1))
            print("Doi vai phut roi chay lai workflow, no se tiep tuc tu cho dang do.")
            break
        if ma.startswith("LOI_MANG"):
            loi_khac[ma] = loi_khac.get(ma, 0) + 1

        ket_qua[dong] = (ipa or TRONG, audio or TRONG)
        if ipa and audio:
            thong_ke["co_ca_hai"] += 1
            if len(vi_du) < 5:
                vi_du.append((word, ipa, audio))
        elif ipa:
            thong_ke["chi_ipa"] += 1
        elif audio:
            thong_ke["chi_audio"] += 1
        else:
            thong_ke["khong_co"] += 1

        if thu_tu % 50 == 0:
            print("  ... da tra %d/%d" % (thu_tu, len(dot)))
        time.sleep(nghi)

    if not ket_qua:
        die("Khong tra cuu duoc tu nao.", "Xem cac dong loi phia tren.")

    # --- Ghi nguoc vao Sheet theo lo lien tiep ---
    print("")
    print("Dang ghi %d dong vao Sheet..." % len(ket_qua))
    cac_dong = sorted(ket_qua)
    khoi = []
    dau = truoc = cac_dong[0]
    for d in cac_dong[1:]:
        if d == truoc + 1:
            truoc = d
        else:
            khoi.append((dau, truoc))
            dau = truoc = d
    khoi.append((dau, truoc))

    yeu_cau = []
    for a, b in khoi:
        yeu_cau.append({"range": "G%d:G%d" % (a, b),
                        "values": [[ket_qua[d][1]] for d in range(a, b + 1)]})
        yeu_cau.append({"range": "W%d:W%d" % (a, b),
                        "values": [[ket_qua[d][0]] for d in range(a, b + 1)]})
    try:
        ws.batch_update(yeu_cau, value_input_option="RAW")
    except Exception as e:
        die("Ghi vao Sheet that bai: %s" % e,
            "Kiem tra quyen Editor cua service account. Du lieu lan chay nay chua duoc luu.")

    print("Ghi xong (%d khoi, %d yeu cau)." % (len(khoi), len(yeu_cau)))
    print("")
    print("=" * 60)
    print("KET QUA LAN CHAY NAY")
    print("=" * 60)
    print("Co ca IPA va audio : %d" % thong_ke["co_ca_hai"])
    print("Chi co IPA         : %d" % thong_ke["chi_ipa"])
    print("Chi co audio       : %d" % thong_ke["chi_audio"])
    print("Khong co gi (404)  : %d" % thong_ke["khong_co"])
    if loi_khac:
        print("Loi mang           : " + ", ".join("%s=%d" % kv for kv in loi_khac.items()))
    print("")
    if vi_du:
        print("Vai dong mau:")
        for w, i, a in vi_du:
            print("  %-16s %-22s %s" % (w, i, a[:64]))
    con_lai = len(can_lam) - len(ket_qua)
    print("")
    if con_lai > 0:
        print(">> Con %d tu chua tra. Chay lai workflow nay them lan nua." % con_lai)
    else:
        print(">> Da tra het toan bo tu. Khong can chay lai.")
    print("=" * 60)


if __name__ == "__main__":
    main()
