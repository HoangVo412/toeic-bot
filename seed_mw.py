# -*- coding: utf-8 -*-
"""
Nap phien am (IPA) va link audio tu Merriam-Webster Learner's Dictionary.

VI SAO DOI NGUON:
  * api.dictionaryapi.dev chap chon: mot nua request tra HTTP 522, do tre ~20 giay.
  * Learner's Dictionary tra truong "ipa" (IPA that, vd "ˈæpəl") chu khong phai
    he ky hieu rieng cua Merriam-Webster nhu ban Collegiate ("ˈdäk-tər").
    -> lay duoc CA phien am LAN audio trong mot lan goi.

GHI VAO:
  cot G  AudioURL   - link mp3
  cot W  IPA_API    - phien am
  cot X  NguonPA    - 'mw' hoac 'dev', de biet dong nao lay tu dau

KHONG ghi de cot IPA goc (cot D).
Mac dinh chi lam nhung dong CHUA co du lieu that. Dat GHI_DE=1 de lay lai
toan bo bang nguon Merriam-Webster cho dong nhat.
"""
import os
import sys
import json
import time
import re
import threading
from urllib.parse import quote
from concurrent.futures import ThreadPoolExecutor

API = "https://www.dictionaryapi.com/api/v3/references/learners/json/"
MEDIA = "https://media.merriam-webster.com/audio/prons/en/us/mp3/%s/%s.mp3"
COT_WORD = 2       # B
COT_AUDIO = 7      # G
COT_IPA_API = 23   # W
COT_NGUON = 24     # X
TRONG = "-"
HAN_MUC_NGAY = 1000
DUNG_O = 950       # chua lai 50 luot phong khi can chay lai


def die(ly_do, huong_xu_ly=""):
    print("")
    print("=" * 62)
    print("THAT BAI: " + ly_do)
    if huong_xu_ly:
        print("HUONG XU LY: " + huong_xu_ly)
    print("=" * 62)
    sys.exit(1)


def thu_muc_audio(ten_file):
    """Quy tac dung URL audio, theo tai lieu Merriam-Webster:
       bat dau bang 'bix' -> bix; 'gg' -> gg; chu so hoac dau cau -> number;
       con lai -> ky tu dau tien.
       Vi du tai lieu: '3d000001' -> .../number/3d000001.mp3
    """
    if ten_file.startswith("bix"):
        return "bix"
    if ten_file.startswith("gg"):
        return "gg"
    if re.match(r"^[^a-zA-Z]", ten_file):
        return "number"
    return ten_file[0]


def chuan_ipa(s):
    s = (s or "").strip()
    if not s:
        return ""
    return "/" + s.strip("/") + "/"


def doc_ket_qua(du_lieu, word):
    """Tra ve (ipa, audio_url).
    MW tra ve mang chuoi goi y chinh ta khi khong tim thay -> coi nhu khong co.
    Uu tien ban ghi co meta.id trung ten tu (id co the la 'apple' hoac 'apple:1').
    """
    if not isinstance(du_lieu, list) or not du_lieu:
        return "", ""
    if isinstance(du_lieu[0], str):      # danh sach goi y chinh ta
        return "", ""

    w = word.lower()
    khop_han = []    # meta.id dung bang ten tu, vd "order"
    khop_dong_am = []  # meta.id dang "order:2"
    du_phong = []
    for e in du_lieu:
        if not isinstance(e, dict):
            continue
        ma = str((e.get("meta") or {}).get("id", "")).lower()
        goc = ma.split(":")[0]
        if ma == w:
            khop_han.append(e)
        elif goc == w:
            khop_dong_am.append(e)
        else:
            du_phong.append(e)

    for nhom in (khop_han, khop_dong_am, du_phong):
        for e in nhom:
            for ph in ((e.get("hwi") or {}).get("prs") or []):
                if not isinstance(ph, dict):
                    continue
                ipa = chuan_ipa(ph.get("ipa"))
                ten = ((ph.get("sound") or {}).get("audio") or "").strip()
                audio = MEDIA % (thu_muc_audio(ten), ten) if ten else ""
                if ipa or audio:
                    return ipa, audio
    return "", ""


class TraCuu(object):
    """Tra ve (ipa, audio, trang_thai).
    'OK'       -> ghi vao Sheet
    'KHONG_CO' -> MW khong co tu nay, ghi dau '-'
    'HET_QUOTA'-> dung han
    con lai    -> loi tam thoi, KHONG ghi gi
    """

    def __init__(self, key, so_lan_thu, tmo):
        import requests
        self._requests = requests
        self.key = key
        self.so_lan_thu = so_lan_thu
        self.tmo = tmo
        self._cb = threading.local()
        self.dem = 0
        self.khoa = threading.Lock()

    def _phien(self):
        s = getattr(self._cb, "s", None)
        if s is None:
            s = self._requests.Session()
            self._cb.s = s
        return s

    def _mot_lan(self, word):
        with self.khoa:
            if self.dem >= DUNG_O:
                return "", "", "HET_QUOTA"
            self.dem += 1
        url = API + quote(word.lower()) + "?key=" + self.key
        try:
            r = self._phien().get(url, timeout=self.tmo)
        except Exception as e:
            return "", "", "LOI_MANG:" + type(e).__name__
        if r.status_code == 200:
            try:
                du_lieu = r.json()
            except Exception:
                return "", "", "HTTP:JSON_HONG"
            ipa, audio = doc_ket_qua(du_lieu, word)
            return ipa, audio, ("OK" if (ipa or audio) else "KHONG_CO")
        if r.status_code in (401, 403):
            return "", "", "HTTP:SAI_KEY"
        if r.status_code == 404:
            return "", "", "KHONG_CO"
        return "", "", "HTTP:%d" % r.status_code

    def __call__(self, word):
        cuoi = "LOI_MANG:ChuaChay"
        for lan in range(self.so_lan_thu):
            ipa, audio, tt = self._mot_lan(word)
            if tt in ("OK", "KHONG_CO", "HET_QUOTA", "HTTP:SAI_KEY"):
                return ipa, audio, tt
            cuoi = tt
            if lan < self.so_lan_thu - 1:
                time.sleep(1.5 * (lan + 1))
        return "", "", cuoi


def main():
    sa_raw = os.environ.get("GOOGLE_SA_JSON", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    mw_key = (os.environ.get("MW_KEY") or "").strip()
    ghi_de = (os.environ.get("GHI_DE") or "").strip().lower() in ("1", "true", "yes")

    def so(ten, mac_dinh):
        try:
            return float(os.environ.get(ten) or mac_dinh)
        except ValueError:
            return float(mac_dinh)

    lo = int(so("BATCH_SIZE", 500))
    luong = max(1, min(10, int(so("MAX_WORKERS", 5))))
    so_lan_thu = max(1, min(4, int(so("RETRIES", 2))))
    tmo = so("READ_TIMEOUT", 20)

    print("=" * 62)
    print("CAU HINH DANG DUNG")
    print("=" * 62)
    print("Nguon             : Merriam-Webster Learner's Dictionary")
    print("SHEET_ID          : " + (sheet_id or "(TRONG)"))
    print("GOOGLE_SA_JSON    : " + ("co, %d ky tu" % len(sa_raw) if sa_raw else "(TRONG)"))
    print("MW_KEY            : " + ("co, %d ky tu" % len(mw_key) if mw_key else "(TRONG)"))
    print("BATCH_SIZE        : %d tu" % lo)
    print("MAX_WORKERS       : %d luong" % luong)
    print("RETRIES           : %d lan" % so_lan_thu)
    print("READ_TIMEOUT      : %.0f giay" % tmo)
    print("GHI_DE            : " + ("BAT - lay lai ca nhung dong da co du lieu"
                                    if ghi_de else "tat - chi lam dong con trong"))
    print("Han muc           : %d luot/ngay, script dung o %d" % (HAN_MUC_NGAY, DUNG_O))
    print("")

    if not sheet_id:
        die("Bien SHEET_ID chua toi duoc script.", "Kiem tra tab Variables cua repo.")
    if not sa_raw:
        die("Bien GOOGLE_SA_JSON chua toi duoc script.", "Kiem tra tab Secrets cua repo.")
    if not mw_key:
        die("Bien MW_KEY chua toi duoc script.",
            "Tao secret MW_KEY trong repo, gia tri la API key cua bo Learner's.")
    try:
        sa = json.loads(sa_raw)
    except Exception as e:
        die("GOOGLE_SA_JSON khong phai JSON hop le (%s)." % e, "Dan lai nguyen van file .json.")

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

    def co_tieu_de(cot, ten):
        return len(tieu_de) >= cot and tieu_de[cot - 1].strip() == ten

    if not co_tieu_de(COT_IPA_API, "IPA_API"):
        die("O W1 chua co tieu de 'IPA_API'.", "Go chinh xac  IPA_API  vao o W1.")
    if not co_tieu_de(COT_NGUON, "NguonPA"):
        die("O X1 chua co tieu de 'NguonPA'.", "Go chinh xac  NguonPA  vao o X1.")

    tat_ca = ws.get_all_values()
    print("Tab TuVung co %d dong du lieu." % (len(tat_ca) - 1))

    can_lam = []
    da_xong = 0
    for i, row in enumerate(tat_ca[1:], start=2):
        def o(idx):
            return row[idx - 1].strip() if len(row) >= idx else ""
        word = o(COT_WORD)
        if not word:
            continue
        gia_tri = o(COT_IPA_API)
        co_that = gia_tri and gia_tri != TRONG
        if co_that and not ghi_de:
            da_xong += 1
            continue
        can_lam.append((i, word))

    print("Da co du lieu that  : %d" % da_xong)
    print("Can tra              : %d" % len(can_lam))
    if not can_lam:
        print("")
        print("Khong con gi de lam.")
        return

    dot = can_lam[:lo]
    print("Lo nay xu ly         : %d tu" % len(dot))
    print("")

    tra = TraCuu(mw_key, so_lan_thu, tmo)
    ket_qua = {}
    tk = {"OK": 0, "KHONG_CO": 0, "BO_QUA": 0}
    ly_do = {}
    vi_du = []
    khoa = threading.Lock()
    dung = {"sai_key": False, "het_quota": False}
    bat_dau = time.time()

    def lam_mot(cap):
        dong, word = cap
        if dung["sai_key"] or dung["het_quota"]:
            return
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
                if tt == "HTTP:SAI_KEY":
                    dung["sai_key"] = True
                if tt == "HET_QUOTA":
                    dung["het_quota"] = True

    for vt in range(0, len(dot), 100):
        cum = dot[vt:vt + 100]
        with ThreadPoolExecutor(max_workers=luong) as ex:
            list(ex.map(lam_mot, cum))
        print("  ... %d/%d tu  |  lay duoc %d  |  da goi %d luot  |  %.1f phut"
              % (min(vt + 100, len(dot)), len(dot), tk["OK"], tra.dem,
                 (time.time() - bat_dau) / 60))
        if dung["sai_key"]:
            print("")
            print("DUNG: API tra ve loi xac thuc. Kiem tra lai MW_KEY.")
            break
        if dung["het_quota"]:
            print("")
            print("DUNG: da cham nguong %d luot cua hom nay." % DUNG_O)
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
            yeu_cau.append({"range": "W%d:X%d" % (a, b),
                            "values": [[ket_qua[d][0], "mw"] for d in range(a, b + 1)]})
        try:
            ws.batch_update(yeu_cau, value_input_option="RAW")
        except Exception as e:
            die("Ghi vao Sheet that bai: %s" % e, "Kiem tra quyen Editor.")
        print("Ghi xong (%d khoi)." % len(khoi))
    else:
        print("")
        print("Khong co dong nao de ghi.")

    tong = tk["OK"] + tk["KHONG_CO"] + tk["BO_QUA"]
    print("")
    print("=" * 62)
    print("KET QUA LAN CHAY NAY  (%.1f phut)" % ((time.time() - bat_dau) / 60))
    print("=" * 62)
    print("Lay duoc du lieu       : %d" % tk["OK"])
    print("MW khong co tu nay     : %d" % tk["KHONG_CO"])
    print("Bo qua do loi tam thoi : %d  (KHONG ghi gi, se tra lai lan sau)" % tk["BO_QUA"])
    print("So luot API da dung    : %d / %d" % (tra.dem, HAN_MUC_NGAY))
    if tong:
        print("Ty le thanh cong       : %.0f%%" % (100.0 * tk["OK"] / tong))
    if ly_do:
        print("")
        print("Chi tiet loi:")
        for k, v in sorted(ly_do.items(), key=lambda x: -x[1]):
            ct = ""
            if k == "HTTP:SAI_KEY":
                ct = "  <- key sai, hoac key nay khong thuoc bo Learner's"
            elif k == "HET_QUOTA":
                ct = "  <- cham nguong an toan, doi sang ngay mai"
            elif k == "HTTP:429":
                ct = "  <- goi qua day, giam MAX_WORKERS"
            print("   %-24s %4d lan%s" % (k, v, ct))
    if vi_du:
        print("")
        print("Vai dong mau:")
        for w, i, a in vi_du:
            print("   %-16s %-20s %s" % (w, i, a[:62]))
    con = len(can_lam) - len(ket_qua)
    print("")
    if dung["sai_key"]:
        print(">> Sua MW_KEY roi chay lai.")
    elif dung["het_quota"]:
        print(">> Het han muc hom nay. Chay tiep vao ngay mai.")
    elif con > 0:
        print(">> Con khoang %d tu. Chay lai workflow nay." % con)
    else:
        print(">> Da xong toan bo.")
    print("=" * 62)


if __name__ == "__main__":
    main()
