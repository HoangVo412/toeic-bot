# -*- coding: utf-8 -*-
"""
Sinh 4 cau vi du + ban dich tieng Viet cho tung tu, bang Gemini.

BAN v2 - sua theo ket qua lan chay dau (8/40 tu dat):
  * maxOutputTokens 4096 -> 8192. Do 8 tu moi lan can ~4400 token, tran cu bi
    tran khien JSON bi cat giua chung, script bao "JSONDecodeError" vo nghia.
  * WORDS_PER_CALL mac dinh 8 -> 6, de cach xa tran.
  * Bat finishReason == MAX_TOKENS va bao dung ly do thay vi loi JSON.
  * XOAY VONG MODEL khi gap 503. Ban truoc chon mot model roi bam mai vao no;
    'gemini-flash-latest' la alias tro ve chinh model dang nghen nen thu lai vo ich.
    Nay xac thuc san nhieu model va nhay sang model KHAC DONG khi bi qua tai.
  * Giai lao dai hon giua cac lan thu 503.

BA LOP CHAN LOI giu nguyen:
  1. Prompt rang buoc nghia tieng Viet da chuan hoa o cot E.
  2. Tu kiem co hoc: cau phai thuc su chua tu do, kiem bang ranh gioi tu.
  3. Ban dich phai la tieng Viet co dau.

Ghi vao cot H..O (VD1, Dich1 ... VD4, Dich4).
"""
import os
import re
import sys
import json
import time
import unicodedata

BASE = "https://generativelanguage.googleapis.com/v1beta"
COT_WORD, COT_POS, COT_NGHIA = 2, 3, 5      # B, C, E
COT_VD1 = 8                                  # H
SO_CAU = 4
TRAN_TOKEN = 8192

# Xep xen ke cac DONG khac nhau, de khi mot dong nghen thi nhay sang dong khac.
# LUU Y: ten model bi khai tu theo thoi gian. Log ngay 07/09/2026 cho thay
# gemini-2.0-flash / 2.5-flash / 2.5-flash-lite deu da tra 404.
# Neu moi ten duoi day deu hong, script tu hoi API danh sach model cua tai khoan.
MODEL_UU_TIEN = [
    "gemini-flash-latest",
    "gemini-3-flash-preview",
    "gemini-flash-lite-latest",
    "gemini-3.6-flash",
    "gemini-2.5-flash",
]
SO_MODEL_XAC_THUC = 3        # xac thuc san bao nhieu model truoc khi chay
DOI_MODEL_SAU = 2            # bao nhieu lan 503 lien tiep thi doi model
QUAY_VE_SAU = 3              # bao nhieu nhom thanh cong thi quay lai model chinh


def die(ly_do, huong_xu_ly=""):
    print("")
    print("=" * 62)
    print("THAT BAI: " + ly_do)
    if huong_xu_ly:
        print("HUONG XU LY: " + huong_xu_ly)
    print("=" * 62)
    sys.exit(1)


# ---------------------------------------------------------------- tu kiem
def bien_the(w):
    """Sinh co hoc cac dang thuong gap cua mot tu, de kiem cau co chua no khong."""
    w = w.lower().strip()
    if not w:
        return {w}

    # Tu dang "according (to)": chap nhan ca "according to" lan "according"
    if "(" in w:
        day_du = re.sub(r"[()]", "", w)
        day_du = re.sub(r"\s+", " ", day_du).strip()
        rut_gon = re.sub(r"\s*\([^)]*\)", "", w).strip()
        ds = {x for x in (day_du, rut_gon) if x}
        return ds

    ds = {w}
    if " " in w:
        return ds                      # cum tu nhieu chu: kiem nguyen cum
    ds |= {w + "s", w + "es", w + "d", w + "ed", w + "ing"}
    if w.endswith("e"):
        ds |= {w[:-1] + "ing", w[:-1] + "ed", w[:-1] + "es"}
    if w.endswith("y") and len(w) > 2 and w[-2] not in "aeiou":
        ds |= {w[:-1] + "ies", w[:-1] + "ied"}
    if len(w) > 2 and w[-1] not in "aeiouwxy" and w[-2] in "aeiou" and w[-3] not in "aeiou":
        ds |= {w + w[-1] + "ed", w + w[-1] + "ing"}
    return ds


def cau_co_chua(cau, word):
    thap = cau.lower()
    for bt in bien_the(word):
        if re.search(r"(?<!\w)" + re.escape(bt) + r"(?!\w)", thap, re.UNICODE):
            return True
    return False


def co_dau_tieng_viet(s):
    return any(unicodedata.category(c) == "Mn"
               for c in unicodedata.normalize("NFD", s)) or "đ" in s.lower()


def doc_json(txt):
    """Doc JSON. Neu bi cat giua chung thi van vot lay cac muc HOAN CHINH.
    Tra ve (du_lieu, da_va) - da_va = True nghia la ban goc hong nhung cuu duoc.
    """
    try:
        return json.loads(txt), False
    except Exception:
        pass

    # Quet thu cong: lay tung object can bang ngoac trong mang "ket_qua"
    vt = txt.find('"ket_qua"')
    if vt < 0:
        return None, False
    vt = txt.find("[", vt)
    if vt < 0:
        return None, False

    muc = []
    i = vt + 1
    n = len(txt)
    while i < n:
        while i < n and txt[i] not in "{]":
            i += 1
        if i >= n or txt[i] == "]":
            break
        dau = i
        sau = 0
        trong_chuoi = False
        thoat = False
        while i < n:
            c = txt[i]
            if thoat:
                thoat = False
            elif c == "\\":
                thoat = True
            elif c == '"':
                trong_chuoi = not trong_chuoi
            elif not trong_chuoi:
                if c == "{":
                    sau += 1
                elif c == "}":
                    sau -= 1
                    if sau == 0:
                        i += 1
                        break
            i += 1
        if sau != 0:
            break                      # object cuoi bi cat, bo
        try:
            muc.append(json.loads(txt[dau:i]))
        except Exception:
            pass
    if not muc:
        return None, False
    return {"ket_qua": muc}, True


# ---------------------------------------------------------------- Gemini
class Gemini(object):
    def __init__(self, key):
        import requests
        self.r = requests
        self.key = key
        self.dung_duoc = []       # danh sach model da xac thuc
        self.vi_tri = 0           # dang dung model nao trong danh sach
        self.so_lan_goi = 0
        self.lan_doi_model = 0
        self.so_lan_va_json = 0
        self._503_lien_tiep = 0
        self._thanh_cong_tren_du_phong = 0

    @property
    def model(self):
        return self.dung_duoc[self.vi_tri] if self.dung_duoc else None

    def _thu_model(self, ten):
        url = "%s/models/%s:generateContent?key=%s" % (BASE, ten, self.key)
        body = {"contents": [{"parts": [{"text": "Reply with the single word: ok"}]}],
                "generationConfig": {"maxOutputTokens": 20}}
        try:
            r = self.r.post(url, json=body, timeout=45)
        except Exception as e:
            return False, type(e).__name__
        if r.status_code == 200:
            return True, ""
        try:
            mo_ta = r.json().get("error", {}).get("message", "")[:110]
        except Exception:
            mo_ta = r.text[:110]
        return False, "HTTP %d: %s" % (r.status_code, mo_ta)

    def _do_danh_sach(self):
        try:
            r = self.r.get("%s/models?key=%s" % (BASE, self.key), timeout=45)
            if r.status_code != 200:
                return []
            ds = []
            for m in r.json().get("models", []):
                ten = m.get("name", "").replace("models/", "")
                if "generateContent" in (m.get("supportedGenerationMethods") or []):
                    ds.append(ten)
            uu = [t for t in ds if "flash" in t and "thinking" not in t]
            return uu + [t for t in ds if t not in uu]
        except Exception:
            return []

    def chon_model(self):
        print("Dang xac thuc model (can it nhat %d de co duong lui khi 503)..."
              % SO_MODEL_XAC_THUC)
        for ten in MODEL_UU_TIEN:
            if len(self.dung_duoc) >= SO_MODEL_XAC_THUC:
                break
            ok, ly_do = self._thu_model(ten)
            print("   %-26s %s" % (ten, "DUNG DUOC" if ok else "khong: " + ly_do))
            if ok:
                self.dung_duoc.append(ten)
        if len(self.dung_duoc) < SO_MODEL_XAC_THUC:
            print("   Chua du. Dang hoi API danh sach model cua tai khoan...")
            for ten in self._do_danh_sach():
                if len(self.dung_duoc) >= SO_MODEL_XAC_THUC:
                    break
                if ten in self.dung_duoc:
                    continue
                ok, ly_do = self._thu_model(ten)
                print("   %-26s %s" % (ten, "DUNG DUOC" if ok else "khong: " + ly_do))
                if ok:
                    self.dung_duoc.append(ten)
        if not self.dung_duoc:
            die("Khong tim duoc model Gemini nao dung duoc.",
                "Kiem tra GEMINI_KEY con han muc khong, va Generative Language API "
                "da bat trong project chua.")
        print("")
        print("Model se dung : %s" % ", ".join(self.dung_duoc))

    def _doi_model(self):
        if len(self.dung_duoc) < 2:
            return False
        self.vi_tri = (self.vi_tri + 1) % len(self.dung_duoc)
        self.lan_doi_model += 1
        self._503_lien_tiep = 0
        print("      -> chuyen sang model %s" % self.model)
        return True

    def bao_thanh_cong(self):
        """Goi sau moi nhom lam duoc. Neu dang chay model du phong va da on
        dinh mot luc thi quay ve model chinh - tranh bam mai vao model yeu."""
        if self.vi_tri == 0:
            return
        self._thanh_cong_tren_du_phong += 1
        if self._thanh_cong_tren_du_phong >= QUAY_VE_SAU:
            self.vi_tri = 0
            self._thanh_cong_tren_du_phong = 0
            self._503_lien_tiep = 0
            print("      -> quay lai model chinh %s" % self.model)

    def sinh(self, prompt, so_lan_thu=3):
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": TRAN_TOKEN,
                                 "responseMimeType": "application/json"},
        }
        for lan in range(so_lan_thu):
            url = "%s/models/%s:generateContent?key=%s" % (BASE, self.model, self.key)
            self.so_lan_goi += 1
            try:
                r = self.r.post(url, json=body, timeout=180)
            except Exception as e:
                if lan == so_lan_thu - 1:
                    return None, "LOI_MANG:" + type(e).__name__
                time.sleep(5 * (lan + 1))
                continue

            if r.status_code == 200:
                self._503_lien_tiep = 0
                try:
                    kq = r.json()
                    cand = (kq.get("candidates") or [{}])[0]
                    ly_do_dung = cand.get("finishReason", "")
                    if ly_do_dung == "MAX_TOKENS":
                        return None, "BI_CAT_MAX_TOKENS"
                    txt = cand["content"]["parts"][0]["text"]
                except Exception as e:
                    return None, "KHONG_DOC_DUOC_PHAN_HOI:%s" % type(e).__name__
                try:
                    return json.loads(txt), ""
                except Exception:
                    du_lieu, da_va = doc_json(txt)
                    if du_lieu is not None:
                        self.so_lan_va_json += 1
                        return du_lieu, "VA_JSON"
                    return None, "JSON_HONG"

            if r.status_code == 429:
                return None, "HET_HAN_MUC"       # RPD la rang buoc that

            if r.status_code == 503:
                self._503_lien_tiep += 1
                if self._503_lien_tiep >= DOI_MODEL_SAU and self._doi_model():
                    continue                      # thu lai ngay bang model khac
                if lan == so_lan_thu - 1:
                    return None, "QUA_TAI_503"
                time.sleep(10 * (lan + 1))
                continue

            return None, "HTTP:%d" % r.status_code
        return None, "HET_LAN_THU"


# ---------------------------------------------------------------- prompt
def dung_prompt(nhom):
    dong = []
    for w, pos, nghia in nhom:
        dong.append('- word: "%s" | part of speech: "%s" | nghia tieng Viet: "%s"'
                    % (w, pos, nghia))
    ds = "\n".join(dong)
    return """Ban la giao vien luyen thi TOEIC cho nguoi Viet di lam van phong.

Voi MOI tu duoi day, viet %d cau vi du tieng Anh khac nhau, kem ban dich tieng Viet.

DANH SACH TU:
%s

YEU CAU BAT BUOC:
1. Cau phai dung dung NGHIA TIENG VIET da ghi o tren. Neu tu co nhieu nghia,
   chi dung nghia da ghi, khong dung nghia khac.
2. Moi cau PHAI chua chinh tu do (duoc phep chia thi, so nhieu, dang -ing/-ed).
3. Boi canh: cong so, kinh doanh, van phong, du lich cong tac, nha hang khach san
   - dung boi canh thuong gap trong de thi TOEIC. Khong dung boi canh hoc thuat,
   van chuong, hay chinh tri.
4. Do dai cau: 10 den 20 tu. Ngu phap va tu vung o muc trung cap.
5. Bon cau cua cung mot tu phai khac nhau ve tinh huong, khong lap y.
6. Ban dich tieng Viet phai tu nhien, dung van phong hanh chinh - kinh doanh
   quen thuoc voi nguoi Viet, KHONG dich may moc tung chu.

CHI tra ve JSON theo dung dang sau, khong them chu nao khac:
{"ket_qua":[{"word":"...","cau":[{"en":"...","vi":"..."},{"en":"...","vi":"..."},{"en":"...","vi":"..."},{"en":"...","vi":"..."}]}]}
""" % (SO_CAU, ds)


# ---------------------------------------------------------------- main
def main():
    sa_raw = os.environ.get("GOOGLE_SA_JSON", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    gem_key = (os.environ.get("GEMINI_KEY") or "").strip()

    def so(ten, mac_dinh):
        try:
            return float(os.environ.get(ten) or mac_dinh)
        except ValueError:
            return float(mac_dinh)

    lo = int(so("BATCH_SIZE", 60))
    moi_lan = max(3, min(10, int(so("WORDS_PER_CALL", 6))))
    tran_goi = int(so("MAX_CALLS", 40))
    chi_thu = (os.environ.get("CHI_THU") or "").strip().lower() in ("1", "true", "yes")

    print("=" * 62)
    print("CAU HINH DANG DUNG")
    print("=" * 62)
    print("SHEET_ID        : " + (sheet_id or "(TRONG)"))
    print("GOOGLE_SA_JSON  : " + ("co, %d ky tu" % len(sa_raw) if sa_raw else "(TRONG)"))
    print("GEMINI_KEY      : " + ("co, %d ky tu" % len(gem_key) if gem_key else "(TRONG)"))
    print("BATCH_SIZE      : %d tu" % lo)
    print("WORDS_PER_CALL  : %d tu moi lan goi" % moi_lan)
    print("MAX_CALLS       : %d lan goi toi da" % tran_goi)
    print("maxOutputTokens : %d  (uoc tinh can ~%d cho %d tu)"
          % (TRAN_TOKEN, int(moi_lan * 340 * 1.6), moi_lan))
    print("CHI_THU         : " + ("BAT - IN RA MAN HINH, KHONG GHI VAO SHEET"
                                  if chi_thu else "tat - se ghi vao Sheet"))
    print("")

    if not sheet_id:
        die("Bien SHEET_ID chua toi duoc script.")
    if not sa_raw:
        die("Bien GOOGLE_SA_JSON chua toi duoc script.")
    if not gem_key:
        die("Bien GEMINI_KEY chua toi duoc script.", "Tao secret GEMINI_KEY trong repo.")
    try:
        sa = json.loads(sa_raw)
    except Exception as e:
        die("GOOGLE_SA_JSON khong phai JSON hop le (%s)." % e)

    import gspread
    from google.oauth2.service_account import Credentials

    scopes = ["https://www.googleapis.com/auth/spreadsheets",
              "https://www.googleapis.com/auth/drive"]
    try:
        gc = gspread.authorize(Credentials.from_service_account_info(sa, scopes=scopes))
        sh = gc.open_by_key(sheet_id)
        ws = sh.worksheet("TuVung")
    except Exception as e:
        die("Khong mo duoc tab TuVung: %s" % e)

    tat_ca = ws.get_all_values()
    can_lam = []
    da_co = 0
    for i, row in enumerate(tat_ca[1:], start=2):
        def o(idx):
            return row[idx - 1].strip() if len(row) >= idx else ""
        word = o(COT_WORD)
        if not word:
            continue
        if o(COT_VD1):
            da_co += 1
            continue
        can_lam.append((i, word, o(COT_POS), o(COT_NGHIA)))

    print("Da co cau vi du : %d" % da_co)
    print("Can sinh        : %d" % len(can_lam))
    if not can_lam:
        print("\nKhong con gi de lam.")
        return

    dot = can_lam[:lo]
    print("Lo nay xu ly    : %d tu" % len(dot))
    print("")

    gem = Gemini(gem_key)
    gem.chon_model()
    print("")

    ten_theo_dong = {d: w for d, w, _, _ in dot}
    nghia_theo_dong = {d: n for d, _, _, n in dot}

    ket_qua = {}
    loai_bo = []
    loi = {}
    bat_dau = time.time()

    def chay_mot_dot(danh_sach, so_tu_moi_lan, nhan):
        """Chay het mot danh sach tu. Tra ve list cac tu CHUA dat."""
        chua_dat = []
        for vt in range(0, len(danh_sach), so_tu_moi_lan):
            if gem.so_lan_goi >= tran_goi:
                print("  Cham tran %d lan goi. Dung lai." % tran_goi)
                chua_dat += danh_sach[vt:]
                break
            nhom = danh_sach[vt:vt + so_tu_moi_lan]
            du_lieu, ly_do = gem.sinh(dung_prompt([(w, p, n) for _, w, p, n in nhom]))

            if du_lieu is None:
                loi[ly_do] = loi.get(ly_do, 0) + 1
                print("  %s[%d-%d] that bai: %s" % (nhan, vt + 1, vt + len(nhom), ly_do))
                chua_dat += nhom
                if ly_do == "HET_HAN_MUC":
                    print("  Het so lan goi trong ngay (RPD). Dung han.")
                    chua_dat += danh_sach[vt + len(nhom):]
                    dung_han["x"] = True
                    break
                if ly_do == "BI_CAT_MAX_TOKENS":
                    print("  Giam WORDS_PER_CALL xuong roi chay lai.")
                continue

            if ly_do == "VA_JSON":
                loi["VA_JSON"] = loi.get("VA_JSON", 0) + 1

            theo_tu = {}
            for muc in (du_lieu.get("ket_qua") or []):
                if isinstance(muc, dict) and muc.get("word"):
                    theo_tu[str(muc["word"]).lower().strip()] = muc.get("cau") or []

            dat = 0
            for dong, word, pos, nghia in nhom:
                cau_ds = theo_tu.get(word.lower().strip(), [])
                hop_le = []
                for c in cau_ds:
                    if not isinstance(c, dict):
                        continue
                    en = (c.get("en") or "").strip()
                    vi = (c.get("vi") or "").strip()
                    if not en or not vi:
                        continue
                    if not cau_co_chua(en, word):
                        loai_bo.append((word, "cau khong chua tu", en[:58]))
                        continue
                    if not co_dau_tieng_viet(vi):
                        loai_bo.append((word, "ban dich khong phai tieng Viet", vi[:58]))
                        continue
                    hop_le.append((en, vi))
                    if len(hop_le) == SO_CAU:
                        break
                if len(hop_le) == SO_CAU:
                    ket_qua[dong] = hop_le
                    dat += 1
                else:
                    chua_dat.append((dong, word, pos, nghia))
                    if not cau_ds:
                        loai_bo.append((word, "model khong tra ve tu nay", ""))
                    else:
                        loai_bo.append((word, "chi co %d/%d cau dat"
                                        % (len(hop_le), SO_CAU), ""))

            if dat == len(nhom):
                gem.bao_thanh_cong()
            print("  %s[%d-%d] %d/%d tu dat  |  %s  |  da goi %d lan  |  %.1f phut"
                  % (nhan, vt + 1, vt + len(nhom), dat, len(nhom), gem.model,
                     gem.so_lan_goi, (time.time() - bat_dau) / 60))
        return chua_dat

    dung_han = {"x": False}
    con_thieu = chay_mot_dot(dot, moi_lan, "")

    # Vong 2: goi lai rieng nhung tu chua dat, nhom nho hon de model de tra du
    if con_thieu and not dung_han["x"] and gem.so_lan_goi < tran_goi:
        print("")
        print("Vong 2: goi lai %d tu chua dat, nhom %d tu/lan"
              % (len(con_thieu), max(3, moi_lan // 2)))
        loai_bo.append(("---", "--- vong 2 bat dau ---", ""))
        chay_mot_dot(con_thieu, max(3, moi_lan // 2), "v2 ")

    # ------------------------------------------------------------ xuat
    if chi_thu:
        print("")
        print("=" * 62)
        print("BAN THU - KHONG GHI VAO SHEET")
        print("=" * 62)
        for dong in sorted(ket_qua)[:12]:
            print("")
            print("%s  (%s)" % (ten_theo_dong[dong].upper(), nghia_theo_dong[dong]))
            for en, vi in ket_qua[dong]:
                print("   %s" % en)
                print("   -> %s" % vi)
    elif ket_qua:
        print("")
        print("Dang ghi %d dong vao Sheet..." % len(ket_qua))
        yeu_cau = []
        for dong, ds in sorted(ket_qua.items()):
            hang = []
            for en, vi in ds:
                hang += [en, vi]
            yeu_cau.append({"range": "H%d:O%d" % (dong, dong), "values": [hang]})
        try:
            for i in range(0, len(yeu_cau), 200):
                ws.batch_update(yeu_cau[i:i + 200], value_input_option="RAW")
        except Exception as e:
            die("Ghi vao Sheet that bai: %s" % e, "Kiem tra quyen Editor.")
        print("Ghi xong.")

    print("")
    print("=" * 62)
    print("KET QUA LAN CHAY NAY  (%.1f phut)" % ((time.time() - bat_dau) / 60))
    print("=" * 62)
    print("Tu sinh du %d cau dat : %d / %d" % (SO_CAU, len(ket_qua), len(dot)))
    print("So lan goi Gemini     : %d" % gem.so_lan_goi)
    print("So lan doi model      : %d" % gem.lan_doi_model)
    print("So lan phai va JSON   : %d" % gem.so_lan_va_json)
    print("Cau bi loai           : %d" % len(loai_bo))
    if loi:
        print("")
        print("Loi goi API:")
        for k, v in sorted(loi.items(), key=lambda x: -x[1]):
            ct = ""
            if k == "HET_HAN_MUC":
                ct = "  <- het so lan/ngay, doi sang mai"
            elif k == "QUA_TAI_503":
                ct = "  <- Gemini qua tai, khong phai loi han muc"
            elif k == "BI_CAT_MAX_TOKENS":
                ct = "  <- phan hoi dai qua tran, giam WORDS_PER_CALL"
            elif k == "JSON_HONG":
                ct = "  <- model tra ve khong dung dang JSON, khong cuu duoc"
            elif k == "VA_JSON":
                ct = "  <- JSON bi cat nhung da vot duoc phan hoan chinh"
            print("   %-26s %d lan%s" % (k, v, ct))
    if loai_bo:
        print("")
        print("Vai cau bi loai:")
        for w, ly, mau in loai_bo[:10]:
            print("   %-16s %-32s %s" % (w, ly, mau))
    con = len(can_lam) - len(ket_qua)
    print("")
    if con > 0:
        print(">> Con khoang %d tu. Chay lai workflow nay." % con)
    else:
        print(">> Da xong toan bo.")
    print("=" * 62)


if __name__ == "__main__":
    main()
