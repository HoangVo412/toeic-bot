# -*- coding: utf-8 -*-
"""
Sinh 4 cau vi du + ban dich tieng Viet cho tung tu, bang Gemini.

BA LOP CHAN LOI (theo dung thu tu bi sai da gap o cac bot truoc):
  1. Prompt rang buoc nghia: dua nghia tieng Viet DA CHUAN HOA vao prompt,
     khong de model tu chon nghia khac (vd 'plant' = cay thay vi nha may).
  2. Tu kiem co hoc: cau phai THUC SU chua tu do (hoac bien the -s/-ed/-ing...),
     kiem bang RANH GIOI TU. Tu nao truot thi bi loai, khong ghi vao Sheet.
  3. Chuoi model du phong + tu do danh sach model tu API khi moi ten cung deu sai.

Ghi vao cot H..O (VD1, Dich1 ... VD4, Dich4).
Mac dinh chi lam nhung dong CHUA co VD1.
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

# Thu lan luot. Ten model thay doi theo thoi gian nen co buoc tu do o cuoi.
MODEL_UU_TIEN = [
    "gemini-flash-latest",
    "gemini-2.5-flash",
    "gemini-2.0-flash",
    "gemini-flash-lite-latest",
]


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
    ds = {w}
    if not w or " " in w or "(" in w:
        return ds                      # cum tu: kiem nguyen cum
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


# ---------------------------------------------------------------- Gemini
class Gemini(object):
    def __init__(self, key):
        import requests
        self.r = requests
        self.key = key
        self.model = None
        self.so_lan_goi = 0

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
            mo_ta = r.json().get("error", {}).get("message", "")[:120]
        except Exception:
            mo_ta = r.text[:120]
        return False, "HTTP %d: %s" % (r.status_code, mo_ta)

    def _do_danh_sach(self):
        """Khi moi ten cung deu hong, hoi thang API xem tai khoan nay co model nao."""
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
        print("Dang chon model...")
        for ten in MODEL_UU_TIEN:
            ok, ly_do = self._thu_model(ten)
            print("   %-26s %s" % (ten, "DUNG DUOC" if ok else "khong: " + ly_do))
            if ok:
                self.model = ten
                return ten
        print("   Moi ten cung deu hong. Dang hoi API danh sach model...")
        for ten in self._do_danh_sach()[:8]:
            ok, ly_do = self._thu_model(ten)
            print("   %-26s %s" % (ten, "DUNG DUOC" if ok else "khong: " + ly_do))
            if ok:
                self.model = ten
                return ten
        die("Khong tim duoc model Gemini nao dung duoc.",
            "Kiem tra GEMINI_KEY con han muc khong, va API da bat trong project chua.")

    def sinh(self, prompt, so_lan_thu=3):
        url = "%s/models/%s:generateContent?key=%s" % (BASE, self.model, self.key)
        body = {
            "contents": [{"parts": [{"text": prompt}]}],
            "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096,
                                 "responseMimeType": "application/json"},
        }
        for lan in range(so_lan_thu):
            self.so_lan_goi += 1
            try:
                r = self.r.post(url, json=body, timeout=120)
            except Exception as e:
                if lan == so_lan_thu - 1:
                    return None, "LOI_MANG:" + type(e).__name__
                time.sleep(5 * (lan + 1))
                continue
            if r.status_code == 200:
                try:
                    txt = r.json()["candidates"][0]["content"]["parts"][0]["text"]
                    return json.loads(txt), ""
                except Exception as e:
                    return None, "KHONG_DOC_DUOC_JSON:%s" % type(e).__name__
            if r.status_code == 429:
                return None, "HET_HAN_MUC"       # RPD la rang buoc that, thu lai vo ich
            if r.status_code == 503:
                if lan == so_lan_thu - 1:
                    return None, "QUA_TAI_503"
                time.sleep(8 * (lan + 1))
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

    lo = int(so("BATCH_SIZE", 40))
    moi_lan = max(3, min(12, int(so("WORDS_PER_CALL", 8))))
    tran_goi = int(so("MAX_CALLS", 40))
    chi_thu = (os.environ.get("CHI_THU") or "").strip().lower() in ("1", "true", "yes")

    print("=" * 62)
    print("CAU HINH DANG DUNG")
    print("=" * 62)
    print("SHEET_ID        : " + (sheet_id or "(TRONG)"))
    print("GOOGLE_SA_JSON  : " + ("co, %d ky tu" % len(sa_raw) if sa_raw else "(TRONG)"))
    print("GEMINI_KEY      : " + ("co, %d ky tu" % len(gem_key) if gem_key else "(TRONG)"))
    print("BATCH_SIZE      : %d tu" % lo)
    print("WORDS_PER_CALL  : %d tu moi lan goi Gemini" % moi_lan)
    print("MAX_CALLS       : %d lan goi toi da" % tran_goi)
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
    print("Model dang dung : %s" % gem.model)
    print("")

    ket_qua = {}
    loai_bo = []
    loi = {}
    bat_dau = time.time()

    for vt in range(0, len(dot), moi_lan):
        if gem.so_lan_goi >= tran_goi:
            print("Cham tran %d lan goi. Dung lai." % tran_goi)
            break
        nhom = dot[vt:vt + moi_lan]
        du_lieu, ly_do = gem.sinh(dung_prompt([(w, p, n) for _, w, p, n in nhom]))

        if du_lieu is None:
            loi[ly_do] = loi.get(ly_do, 0) + 1
            print("  [%d-%d] that bai: %s" % (vt + 1, vt + len(nhom), ly_do))
            if ly_do == "HET_HAN_MUC":
                print("  Het han muc ngay (RPD). Dung han.")
                break
            continue

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
                    loai_bo.append((word, "cau khong chua tu", en[:60]))
                    continue
                if not co_dau_tieng_viet(vi):
                    loai_bo.append((word, "ban dich khong phai tieng Viet", vi[:60]))
                    continue
                hop_le.append((en, vi))
                if len(hop_le) == SO_CAU:
                    break
            if len(hop_le) == SO_CAU:
                ket_qua[dong] = hop_le
                dat += 1
            else:
                loai_bo.append((word, "chi co %d/%d cau dat" % (len(hop_le), SO_CAU), ""))

        print("  [%d-%d] %d/%d tu dat  |  da goi %d lan  |  %.1f phut"
              % (vt + 1, vt + len(nhom), dat, len(nhom), gem.so_lan_goi,
                 (time.time() - bat_dau) / 60))

    # ------------------------------------------------------------ xuat
    if chi_thu:
        print("")
        print("=" * 62)
        print("BAN THU - KHONG GHI VAO SHEET")
        print("=" * 62)
        for dong in sorted(ket_qua)[:12]:
            word = [w for d, w, _, _ in dot if d == dong][0]
            nghia = [n for d, w, _, n in dot if d == dong][0]
            print("")
            print("%s  (%s)" % (word.upper(), nghia))
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
    print("Tu sinh du %d cau dat : %d" % (SO_CAU, len(ket_qua)))
    print("So lan goi Gemini     : %d" % gem.so_lan_goi)
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
            print("   %-24s %d lan%s" % (k, v, ct))
    if loai_bo:
        print("")
        print("Vai cau bi loai (xem de chinh prompt neu nhieu):")
        for w, ly, mau in loai_bo[:10]:
            print("   %-16s %-32s %s" % (w, ly, mau))
    print("")
    con = len(can_lam) - len(ket_qua)
    if con > 0:
        print(">> Con khoang %d tu. Chay lai workflow nay." % con)
    else:
        print(">> Da xong toan bo.")
    print("=" * 62)


if __name__ == "__main__":
    main()
