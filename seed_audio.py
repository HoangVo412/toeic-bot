# -*- coding: utf-8 -*-
"""
Nap phien am (IPA) va link audio phat am cho tung tu, lay tu Free Dictionary API.

BAN v3 - dieu chinh theo ket qua chan doan tu chinh runner:
  * API tra 200 nhung MAT ~19.7 GIAY moi co byte dau tien.
    Timeout 15s cua ban truoc luon thua -> doi thanh 35s.
  * Khoang mot nua request tra HTTP 522 (Cloudflare: may chu goc khong phan hoi).
    Day la su co phia nha cung cap, KHONG phai chan IP -> khong can proxy.
  * Voi do tre 20s/request, chay tuan tu se mat hang gio -> chay SONG SONG nhieu luong.
  * 522 duoc xu ly nhu loi tam thoi: khong ghi gi vao Sheet, de lan chay sau tra lai.

KHONG ghi de cot IPA goc (cot D). Chi ghi cot G (AudioURL) va W (IPA_API).
"""
import os
import sys
import json
import time
import threading
import unicodedata
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor

API_TRUC_TIEP = "https://api.dictionaryapi.dev/api/v2/entries/en/"
COT_WORD = 2       # B
COT_AUDIO = 7      # G
COT_IPA_API = 23   # W
TRONG = "-"        # da tra roi, API xac nhan khong co du lieu
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36")
KICH_THUOC_CUM = 60      # kiem tra suc khoe API sau moi cum nay
NGUONG_BO_CUOC = 0.05    # ty le thanh cong duoi muc nay thi dung han


def die(ly_do, huong_xu_ly=""):
    print("")
    print("=" * 62)
    print("THAT BAI: " + ly_do)
    if huong_xu_ly:
        print("HUONG XU LY: " + huong_xu_ly)
    print("=" * 62)
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
    trang_thai:
      'OK'       -> lay duoc du lieu, ghi vao Sheet
      'KHONG_CO' -> API xac nhan khong co (404), ghi dau '-' vao Sheet
      con lai    -> loi tam thoi, KHONG ghi gi, lan chay sau tra lai
    """

    def __init__(self, proxy, proxy_secret, tmo_ket_noi, tmo_doc, so_lan_thu):
        import requests
        self._requests = requests
        self.proxy = proxy.rstrip("/") if proxy else ""
        self.secret = proxy_secret
        self.tmo = (tmo_ket_noi, tmo_doc)
        self.so_lan_thu = so_lan_thu
        self._cuc_bo = threading.local()

    def _phien(self):
        # moi luong mot Session rieng: requests.Session khong an toan da luong
        s = getattr(self._cuc_bo, "s", None)
        if s is None:
            s = self._requests.Session()
            self._cuc_bo.s = s
        return s

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
            r = self._phien().get(self._url(w), headers=self._headers(), timeout=self.tmo)
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

        cuoi = "LOI_MANG:ChuaChay"
        for w in ung_vien:
            for lan in range(self.so_lan_thu):
                ipa, audio, tt = self._mot_lan(w)
                if tt == "OK":
                    return ipa, audio, tt
                if tt == "KHONG_CO":
                    cuoi = tt
                    break
                # 4xx that su (tru 429) thi thu lai vo ich
                if tt.startswith("HTTP:4") and tt != "HTTP:429":
                    cuoi = tt
                    break
                cuoi = tt
                if lan < self.so_lan_thu - 1:
                    time.sleep(2.0 * (lan + 1))
        return "", "", cuoi


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

    lo = int(so("BATCH_SIZE", 250))
    luong = max(1, min(12, int(so("MAX_WORKERS", 6))))
    so_lan_thu = max(1, min(5, int(so("RETRIES", 2))))
    tmo_doc = so("READ_TIMEOUT", 35)

    print("=" * 62)
    print("CAU HINH DANG DUNG")
    print("=" * 62)
    print("SHEET_ID          : " + (sheet_id or "(TRONG)"))
    print("GOOGLE_SA_JSON    : " + ("co, %d ky tu" % len(sa_raw) if sa_raw else "(TRONG)"))
    print("DICT_PROXY        : " + (proxy if proxy else "(trong - goi thang API)"))
    print("BATCH_SIZE        : %d tu" % lo)
    print("MAX_WORKERS       : %d luong song song" % luong)
    print("RETRIES           : %d lan moi tu" % so_lan_thu)
    print("READ_TIMEOUT      : %.0f giay  (API do duoc ~19.7s cho byte dau)" % tmo_doc)
    print("RETRY_DASH        : " + ("BAT - tra lai ca cac dong dang co dau '-'"
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
        "  (se tra lai)" if retry_dash else "  (bo qua; dat retry_dash=1 de tra lai)"))
    print("Can tra              : %d" % len(can_lam))
    if not can_lam:
        print("")
        print("Khong con gi de lam.")
        return

    dot = can_lam[:lo]
    print("Lo nay xu ly         : %d tu" % len(dot))
    print("")

    tra = TraCuu(proxy, proxy_secret, 10, tmo_doc, so_lan_thu)
    ket_qua = {}
    tk = {"OK": 0, "KHONG_CO": 0, "BO_QUA": 0}
    ly_do = {}
    vi_du = []
    khoa = threading.Lock()
    bat_dau = time.time()

    def lam_mot(cap):
        dong, word = cap
        ipa, audio, tt = tra(word)
        with khoa:
            if tt == "OK":
                ket_qua[dong] = (ipa or TRONG, audio or TRONG)
                tk["OK"] += 1
                if len(vi_du) < 6:
                    vi_du.append((word, ipa or "-", audio or "-"))
            elif tt == "KHONG_CO":
                ket_qua[dong] = (TRONG, TRONG)
                tk["KHONG_CO"] += 1
            else:
                tk["BO_QUA"] += 1
                ly_do[tt] = ly_do.get(tt, 0) + 1

    bo_cuoc = False
    da_chay = 0
    for vt in range(0, len(dot), KICH_THUOC_CUM):
        cum = dot[vt:vt + KICH_THUOC_CUM]
        with ThreadPoolExecutor(max_workers=luong) as ex:
            list(ex.map(lam_mot, cum))
        da_chay += len(cum)
        xong = tk["OK"] + tk["KHONG_CO"]
        print("  ... %d/%d tu  |  lay duoc %d  |  bo qua %d  |  %.1f phut"
              % (da_chay, len(dot), tk["OK"], tk["BO_QUA"], (time.time() - bat_dau) / 60))
        if da_chay >= KICH_THUOC_CUM and xong < da_chay * NGUONG_BO_CUOC:
            bo_cuoc = True
            print("")
            print("DUNG SOM: sau %d tu chi lay duoc %d. API dang hong nang." % (da_chay, xong))
            break

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

    tong_thu = tk["OK"] + tk["KHONG_CO"] + tk["BO_QUA"]
    print("")
    print("=" * 62)
    print("KET QUA LAN CHAY NAY  (%.1f phut)" % ((time.time() - bat_dau) / 60))
    print("=" * 62)
    print("Lay duoc du lieu       : %d" % tk["OK"])
    print("API xac nhan khong co  : %d" % tk["KHONG_CO"])
    print("Bo qua do loi tam thoi : %d  (KHONG ghi gi, se tra lai lan sau)" % tk["BO_QUA"])
    if tong_thu:
        print("Ty le thanh cong       : %.0f%%" % (100.0 * tk["OK"] / tong_thu))
    if ly_do:
        print("")
        print("Chi tiet loi:")
        for k, v in sorted(ly_do.items(), key=lambda x: -x[1]):
            chu_thich = ""
            if k == "HTTP:522":
                chu_thich = "  <- may chu goc cua API khong phan hoi"
            elif k == "HTTP:429":
                chu_thich = "  <- goi qua day, giam MAX_WORKERS"
            elif k.startswith("LOI_MANG:ReadTimeout"):
                chu_thich = "  <- API cham hon READ_TIMEOUT"
            print("   %-28s %4d lan%s" % (k, v, chu_thich))
    if vi_du:
        print("")
        print("Vai dong mau:")
        for w, i, a in vi_du:
            print("   %-16s %-22s %s" % (w, i, a[:58]))

    con_lai = len(can_lam) - len(ket_qua)
    print("")
    if bo_cuoc:
        print(">> API dang hong nang. Doi vai gio roi chay lai.")
    elif con_lai > 0:
        print(">> Con khoang %d tu chua co du lieu. Chay lai workflow nay." % con_lai)
    else:
        print(">> Da xong toan bo.")
    print("=" * 62)


if __name__ == "__main__":
    main()
