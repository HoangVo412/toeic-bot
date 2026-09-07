# -*- coding: utf-8 -*-
"""
Nap phien am (IPA) va link audio phat am cho tung tu, lay tu Free Dictionary API.

BAN v2 - sua cac loi cua ban dau:
  1. Loi mang bi dem nham thanh "khong co du lieu" roi ghi '-' vao Sheet,
     khien dong do khong bao gio duoc tra lai. Nay loi mang KHONG ghi gi ca.
  2. Khong thu lai ban bo dau khi chuoi giong het ban goc (tra 2 lan vo ich).
  3. Khong co ngat som: 30 tu loi lien tiep van chay het lo, dot 15 phut.
  4. Them thu lai co giai lao khi gap loi tam thoi.
  5. Ho tro goi qua tram trung chuyen Cloudflare (bien DICT_PROXY) khi bi chan IP.
  6. Them che do RETRY_DASH=1 de tra lai nhung dong da bi ghi nham dau '-'.

KHONG ghi de cot IPA goc (cot D). Chi ghi cot G (AudioURL) va W (IPA_API).
"""
import os
import sys
import json
import time
import unicodedata
from urllib.parse import quote

API_TRUC_TIEP = "https://api.dictionaryapi.dev/api/v2/entries/en/"
COT_WORD = 2       # B
COT_AUDIO = 7      # G
COT_IPA_API = 23   # W
TRONG = "-"        # da tra roi, API khong co du lieu
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
NGAT_SOM_SAU = 12  # so loi mang lien tiep thi dung han


def die(ly_do, huong_xu_ly=""):
    print("")
    print("=" * 60)
    print("THAT BAI: " + ly_do)
    if huong_xu_ly:
        print("HUONG XU LY: " + huong_xu_ly)
    print("=" * 60)
    sys.exit(1)


def bo_dau(s):
    return "".join(c for c in unicodedata.normalize("NFD", s)
                   if unicodedata.category(c) != "Mn")


def chon_du_lieu(entries):
    """Tra ve (ipa, audio_url). Uu tien giong My (-us)."""
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


class TraCuu(object):
    """Tra ve (ipa, audio, trang_thai).
    trang_thai: 'OK' | 'KHONG_CO' | 'LOI_MANG:<ten>' | 'HTTP:<ma>'
      OK / KHONG_CO -> ghi vao Sheet
      con lai       -> KHONG ghi gi, de lan sau tra lai
    """

    def __init__(self, session, proxy, proxy_secret, tmo_ket_noi, tmo_doc):
        self.s = session
        self.proxy = proxy.rstrip("/") if proxy else ""
        self.secret = proxy_secret
        self.tmo = (tmo_ket_noi, tmo_doc)

    def _url(self, w):
        if self.proxy:
            return self.proxy + "?w=" + quote(w)
        return API_TRUC_TIEP + quote(w)

    def _headers(self):
        h = {"User-Agent": UA, "Accept": "application/json"}
        if self.proxy and self.secret:
            h["X-Proxy-Secret"] = self.secret
        return h

    def _mot_lan(self, w):
        try:
            r = self.s.get(self._url(w), headers=self._headers(), timeout=self.tmo)
        except Exception as e:
            return "", "", "LOI_MANG:" + type(e).__name__
        if r.status_code == 200:
            try:
                ipa, audio = chon_du_lieu(r.json())
            except Exception:
                return "", "", "HTTP:JSON_HONG"
            return ipa, audio, ("OK" if (ipa or audio) else "KHONG_CO")
        if r.status_code == 404:
            return "", "", "KHONG_CO"
        return "", "", "HTTP:%d" % r.status_code

    def __call__(self, word):
        ung_vien = [word]
        khong_dau = bo_dau(word)
        if khong_dau != word:
            ung_vien.append(khong_dau)

        trang_thai_cuoi = "LOI_MANG:ChuaChay"
        for w in ung_vien:
            for lan in range(3):
                ipa, audio, tt = self._mot_lan(w)
                if tt == "OK":
                    return ipa, audio, tt
                if tt == "KHONG_CO":
                    trang_thai_cuoi = tt
                    break
                if tt.startswith("HTTP:4") and not tt.startswith("HTTP:429"):
                    trang_thai_cuoi = tt
                    break
                trang_thai_cuoi = tt
                time.sleep(1.5 * (lan + 1))
        return "", "", trang_thai_cuoi


def main():
    sa_raw = os.environ.get("GOOGLE_SA_JSON", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    proxy = (os.environ.get("DICT_PROXY") or "").strip()
    proxy_secret = os.environ.get("DICT_PROXY_SECRET", "")
    retry_dash = (os.environ.get("RETRY_DASH") or "").strip().lower() in ("1", "true", "yes")

    def so(ten, mac_dinh):
        try:
            return float(os.environ.get(ten) or mac_dinh)
        except ValueError:
            return float(mac_dinh)

    lo = int(so("BATCH_SIZE", 350))
    nghi = so("DELAY", 0.25)

    print("=" * 60)
    print("CAU HINH DANG DUNG")
    print("=" * 60)
    print("SHEET_ID          : " + (sheet_id or "(TRONG)"))
    print("GOOGLE_SA_JSON    : " + ("co, %d ky tu" % len(sa_raw) if sa_raw else "(TRONG)"))
    print("DICT_PROXY        : " + (proxy if proxy else "(trong - goi thang API)"))
    print("DICT_PROXY_SECRET : " + ("co, %d ky tu" % len(proxy_secret)
                                    if proxy_secret else "(trong)"))
    print("BATCH_SIZE        : %d" % lo)
    print("DELAY             : %.2f giay" % nghi)
    print("RETRY_DASH        : " + ("BAT - tra lai ca nhung dong dang co dau '-'"
                                    if retry_dash else "tat"))
    print("")

    if not sheet_id:
        die("Bien SHEET_ID chua toi duoc script.", "Kiem tra tab Variables cua repo.")
    if not sa_raw:
        die("Bien GOOGLE_SA_JSON chua toi duoc script.", "Kiem tra tab Secrets cua repo.")
    try:
        sa = json.loads(sa_raw)
    except Exception as e:
        die("GOOGLE_SA_JSON khong phai JSON hop le (%s)." % e,
            "Dan lai nguyen van file .json.")

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

    tieu_de = ws.row_values(1)
    if len(tieu_de) < COT_IPA_API or tieu_de[COT_IPA_API - 1].strip() != "IPA_API":
        die("O W1 chua co tieu de 'IPA_API'.", "Go chinh xac  IPA_API  vao o W1.")

    tat_ca = ws.get_all_values()
    print("Tab TuVung co %d dong du lieu." % (len(tat_ca) - 1))

    can_lam = []
    da_co_that = 0
    dang_dau_gach = 0
    for i, row in enumerate(tat_ca[1:], start=2):
        def o(idx):
            return row[idx - 1].strip() if len(row) >= idx else ""
        w_val = o(COT_IPA_API)
        word = o(COT_WORD)
        if not word:
            continue
        if w_val == TRONG:
            dang_dau_gach += 1
            if retry_dash:
                can_lam.append((i, word))
            continue
        if w_val:
            da_co_that += 1
            continue
        can_lam.append((i, word))

    print("Da co du lieu that  : %d" % da_co_that)
    print("Dang danh dau '-'   : %d%s" % (
        dang_dau_gach,
        "  (se tra lai)" if retry_dash else "  (bo qua; dat RETRY_DASH=1 de tra lai)"))
    print("Can tra lan nay     : %d" % len(can_lam))
    if not can_lam:
        print("")
        print("Khong con gi de lam.")
        return

    dot = can_lam[:lo]
    print("Lo nay xu ly        : %d tu (dong %d -> %d)" % (len(dot), dot[0][0], dot[-1][0]))
    print("")

    session = requests.Session()
    tra = TraCuu(session, proxy, proxy_secret, 8, 15)

    ket_qua = {}
    tk = {"OK": 0, "KHONG_CO": 0, "BO_QUA": 0}
    ly_do = {}
    vi_du = []
    loi_lien_tiep = 0
    dung_som = False

    for thu_tu, (dong, word) in enumerate(dot, start=1):
        ipa, audio, tt = tra(word)

        if tt == "OK":
            ket_qua[dong] = (ipa or TRONG, audio or TRONG)
            tk["OK"] += 1
            loi_lien_tiep = 0
            if len(vi_du) < 5:
                vi_du.append((word, ipa or "-", audio or "-"))
        elif tt == "KHONG_CO":
            ket_qua[dong] = (TRONG, TRONG)
            tk["KHONG_CO"] += 1
            loi_lien_tiep = 0
        else:
            tk["BO_QUA"] += 1
            ly_do[tt] = ly_do.get(tt, 0) + 1
            loi_lien_tiep += 1
            if loi_lien_tiep >= NGAT_SOM_SAU:
                dung_som = True
                print("")
                print("NGAT SOM: %d tu lien tiep khong goi duoc API." % loi_lien_tiep)
                print("Ly do gan nhat: %s" % tt)
                print("Dung lai de khoi dot thoi gian vo ich.")
                break

        if thu_tu % 50 == 0:
            print("  ... da tra %d/%d  (lay duoc %d)" % (thu_tu, len(dot), tk["OK"]))
        time.sleep(nghi)

    if ket_qua:
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
            die("Ghi vao Sheet that bai: %s" % e, "Kiem tra quyen Editor.")
        print("Ghi xong (%d khoi)." % len(khoi))
    else:
        print("")
        print("Khong co dong nao de ghi.")

    print("")
    print("=" * 60)
    print("KET QUA LAN CHAY NAY")
    print("=" * 60)
    print("Lay duoc du lieu       : %d" % tk["OK"])
    print("API xac nhan khong co  : %d" % tk["KHONG_CO"])
    print("Bo qua do loi          : %d  (KHONG ghi gi, se tra lai lan sau)" % tk["BO_QUA"])
    if ly_do:
        print("")
        print("Chi tiet loi:")
        for k, v in sorted(ly_do.items(), key=lambda x: -x[1]):
            print("   %-28s %d lan" % (k, v))
    if vi_du:
        print("")
        print("Vai dong mau:")
        for w, i, a in vi_du:
            print("   %-16s %-22s %s" % (w, i, a[:60]))
    print("")
    if dung_som:
        print(">> DUNG SOM. API khong goi duoc tu runner nay.")
        print(">> Chay workflow 'Chan doan mang' truoc khi thu lai.")
    elif tk["BO_QUA"] > tk["OK"]:
        print(">> Ty le loi cao bat thuong. Nen chay 'Chan doan mang'.")
    else:
        con = len(can_lam) - len(dot)
        if con > 0 or tk["BO_QUA"]:
            print(">> Chay lai workflow nay de lam tiep phan con lai.")
        else:
            print(">> Da xong toan bo.")
    print("=" * 60)


if __name__ == "__main__":
    main()
