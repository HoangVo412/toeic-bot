# -*- coding: utf-8 -*-
"""
Logic hoc lai ngat quang (Leitner) cho bot TOEIC.

MODULE NAY THUAN TINH TOAN. Khong doc Sheet, khong goi Telegram.
Nho vay test duoc doc lap bang du lieu gia truoc khi rap vao he thong that.

Bac thang (doc tu CauHinh, mac dinh 1-3-7-16-35-70):
  Tang 0 = chua gui bao gio
  Tang 1..N = dang hoc, moi tang co khoang cach on rieng
  Tang N+1 = THUOC, ra khoi vong on

Quy tac:
  - Bam "Nho"   -> len 1 tang, hen ngay on moi theo tang moi
  - Bam "Quen"  -> LUI 1 tang (khong ve tang 1), hen lai theo tang moi
  - Bam "De sau"-> giu nguyen tang, hen lai ngay mai
  - Bam "Da biet" (chi o lan gui dau) -> danh dau THUOC luon, khong vao vong on
"""
from datetime import date, timedelta

TANG_MAC_DINH = [1, 3, 7, 16, 35, 70]

CHUA_GUI = "CHUA_GUI"
DANG_HOC = "DANG_HOC"
THUOC = "THUOC"
DA_BIET = "DA_BIET"


# ---------------------------------------------------------------- ngay thang
def doc_ngay(s):
    """Doc chuoi 'YYYY-MM-DD'. Tra ve None neu rong hoac sai dinh dang."""
    s = (s or "").strip()
    if not s:
        return None
    s = s.split(" ")[0].split("T")[0]
    try:
        nam, thang, ngay = (int(x) for x in s.split("-"))
        return date(nam, thang, ngay)
    except Exception:
        return None


def ghi_ngay(d):
    return d.isoformat() if d else ""


def so_ngay_con_lai(hom_nay, ngay_thi):
    if not ngay_thi:
        return None
    return (ngay_thi - hom_nay).days


def dang_nuoc_rut(hom_nay, ngay_thi, nguong):
    con = so_ngay_con_lai(hom_nay, ngay_thi)
    return con is not None and 0 <= con <= nguong


# ---------------------------------------------------------------- mot the tu
class The(object):
    """Mot tu va trang thai hoc cua no."""

    def __init__(self, dong, word, nhom="A", tang=0, ngay_on_tiep=None,
                 lan_dau_gui=None, lan_on_cuoi=None, so_nho=0, so_quen=0,
                 trang_thai=CHUA_GUI):
        self.dong = dong
        self.word = word
        self.nhom = (nhom or "A").strip().upper() or "A"
        self.tang = int(tang or 0)
        self.ngay_on_tiep = ngay_on_tiep
        self.lan_dau_gui = lan_dau_gui
        self.lan_on_cuoi = lan_on_cuoi
        self.so_nho = int(so_nho or 0)
        self.so_quen = int(so_quen or 0)
        self.trang_thai = (trang_thai or CHUA_GUI).strip().upper() or CHUA_GUI

    def __repr__(self):
        return "<The %s tang=%d %s on=%s>" % (
            self.word, self.tang, self.trang_thai, ghi_ngay(self.ngay_on_tiep))


class LichHoc(object):
    def __init__(self, cac_tang=None):
        self.tang = list(cac_tang or TANG_MAC_DINH)
        if not self.tang:
            raise ValueError("Danh sach tang khong duoc rong")
        self.tang_cuoi = len(self.tang)

    def khoang_cach(self, tang):
        """So ngay tu lan hoc den lan on ke tiep, ung voi tang hien tai."""
        if tang < 1:
            return self.tang[0]
        if tang > self.tang_cuoi:
            return None
        return self.tang[tang - 1]

    # ------------------------------------------------------ chuyen trang thai
    def gui_lan_dau(self, the, hom_nay):
        the.tang = 1
        the.trang_thai = DANG_HOC
        the.lan_dau_gui = hom_nay
        the.lan_on_cuoi = hom_nay
        the.ngay_on_tiep = hom_nay + timedelta(days=self.khoang_cach(1))
        return the

    def danh_dau_da_biet(self, the, hom_nay):
        the.trang_thai = DA_BIET
        the.tang = self.tang_cuoi + 1
        the.ngay_on_tiep = None
        the.lan_on_cuoi = hom_nay
        if the.lan_dau_gui is None:
            the.lan_dau_gui = hom_nay
        return the

    def tra_loi_nho(self, the, hom_nay):
        the.so_nho += 1
        the.lan_on_cuoi = hom_nay
        the.tang += 1
        if the.tang > self.tang_cuoi:
            the.tang = self.tang_cuoi + 1
            the.trang_thai = THUOC
            the.ngay_on_tiep = None
        else:
            the.trang_thai = DANG_HOC
            the.ngay_on_tiep = hom_nay + timedelta(days=self.khoang_cach(the.tang))
        return the

    def tra_loi_quen(self, the, hom_nay):
        """Lui 1 tang, khong ve tan tang 1. Voi tu da THUOC thi keo tro lai vong on."""
        the.so_quen += 1
        the.lan_on_cuoi = hom_nay
        if the.tang > self.tang_cuoi:          # dang THUOC ma quen -> quay lai
            the.tang = self.tang_cuoi
        else:
            the.tang = max(1, the.tang - 1)
        the.trang_thai = DANG_HOC
        the.ngay_on_tiep = hom_nay + timedelta(days=self.khoang_cach(the.tang))
        return the

    def tra_loi_de_sau(self, the, hom_nay):
        """Giu nguyen tang, chi doi lich sang mai. Khong tinh la nho hay quen."""
        the.ngay_on_tiep = hom_nay + timedelta(days=1)
        if the.trang_thai == CHUA_GUI:
            the.trang_thai = DANG_HOC
        return the


# ---------------------------------------------------------------- chon tu
def den_han_on(the, hom_nay):
    if the.trang_thai in (THUOC, DA_BIET):
        return False
    if the.tang < 1 or the.ngay_on_tiep is None:
        return False
    return the.ngay_on_tiep <= hom_nay


def chon_de_on(cac_the, hom_nay, gioi_han=None):
    """Cac tu den han, uu tien tu QUA HAN LAU NHAT roi den tang thap.
    Tu tang thap = chua vung, on truoc thi tot hon."""
    ds = [t for t in cac_the if den_han_on(t, hom_nay)]
    ds.sort(key=lambda t: (t.ngay_on_tiep, t.tang, t.dong))
    return ds[:gioi_han] if gioi_han else ds


def chon_tu_moi(cac_the, so_luong, thu_tu_nhom=("A", "B"), rng=None):
    """Chon tu chua gui bao gio. Het nhom A moi sang nhom B.
    Trong cung nhom thi chon ngau nhien, de moi ngay khong doc theo thu tu bang chu cai.
    """
    if so_luong <= 0:
        return []
    chua = [t for t in cac_the if t.trang_thai == CHUA_GUI and t.tang == 0]
    ket_qua = []
    for nhom in thu_tu_nhom:
        if len(ket_qua) >= so_luong:
            break
        trong_nhom = [t for t in chua if t.nhom == nhom]
        if rng is not None:
            rng.shuffle(trong_nhom)
        else:
            trong_nhom.sort(key=lambda t: t.dong)
        ket_qua += trong_nhom[:so_luong - len(ket_qua)]
    return ket_qua


def ke_hoach_ngay(cac_the, hom_nay, so_tu_moi, ngay_thi=None,
                  nguong_nuoc_rut=21, thu_tu_nhom=("A", "B"), rng=None,
                  tran_on=45):
    """Tra ve dict mo ta viec can lam hom nay.

    Trong giai doan nuoc rut thi NGUNG nap tu moi, don toan bo suc vao on tap.

    tran_on: so tu on TOI DA mot ngay. Bo nay quan trong: neu nghi hoc mot tuan,
    so tu den han co the len toi gan 200 - qua suc, va hau qua that su la bo luon.
    Phan vuot tran duoc doi sang hom sau, uu tien tu QUA HAN LAU NHAT.
    """
    nuoc_rut = dang_nuoc_rut(hom_nay, ngay_thi, nguong_nuoc_rut)
    tu_moi = [] if nuoc_rut else chon_tu_moi(cac_the, so_tu_moi, thu_tu_nhom, rng)
    den_han = chon_de_on(cac_the, hom_nay)
    if nuoc_rut:
        tran_on = int(tran_on * 1.5)      # nuoc rut thi chiu tai cao hon
    on_tap = den_han[:tran_on] if tran_on else den_han
    return {
        "nuoc_rut": nuoc_rut,
        "con_lai_den_ngay_thi": so_ngay_con_lai(hom_nay, ngay_thi),
        "tu_moi": tu_moi,
        "on_tap": on_tap,
        "ton_lai": max(0, len(den_han) - len(on_tap)),
    }


# ---------------------------------------------------------------- thong ke
def thong_ke(cac_the, hom_nay, lich):
    dang_hoc = [t for t in cac_the if t.trang_thai == DANG_HOC]
    theo_tang = {}
    for t in dang_hoc:
        theo_tang[t.tang] = theo_tang.get(t.tang, 0) + 1
    tong_luot = sum(t.so_nho + t.so_quen for t in cac_the)
    cung_dau = sorted([t for t in cac_the if t.so_quen >= 3],
                      key=lambda t: (-t.so_quen, t.word))
    return {
        "tong_kho": len(cac_the),
        "chua_gui": sum(1 for t in cac_the if t.trang_thai == CHUA_GUI),
        "dang_hoc": len(dang_hoc),
        "thuoc": sum(1 for t in cac_the if t.trang_thai == THUOC),
        "da_biet": sum(1 for t in cac_the if t.trang_thai == DA_BIET),
        "theo_tang": theo_tang,
        "den_han_hom_nay": len(chon_de_on(cac_the, hom_nay)),
        "qua_han": sum(1 for t in cac_the
                       if den_han_on(t, hom_nay) and t.ngay_on_tiep < hom_nay),
        "tong_luot_on": tong_luot,
        "ty_le_nho": (100.0 * sum(t.so_nho for t in cac_the) / tong_luot
                      if tong_luot else 0.0),
        "tu_cung_dau": cung_dau[:5],
    }
