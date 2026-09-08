# -*- coding: utf-8 -*-
"""
Script chinh cua bot TOEIC. Rap moi thu lai:
  Google Sheets  <->  logic Leitner (srs.py)  <->  Telegram  <->  KV cua Worker

CAC CHE DO (dat qua bien VIEC, do Worker gui xuong bang repository_dispatch):
  tu_moi        gui N tu moi buoi sang
  tu_moi_them   nguoi dung go /tuvung - gui them, khong trung tu da gui hom nay
  on_tap        gui cac the den han on
  thong_ke      tra loi /status
  tra_tu        tra loi /tim <tu>
  dong_bo       chi dong bo phan hoi tu KV vao Sheet, khong gui gi

MOI LAN CHAY DEU DONG BO PHAN HOI TRUOC. Nguoi dung bam nut luc nao cung duoc,
Worker giu tam trong KV, den phien chay ke tiep moi ghi vao Sheet.

QUY TAC VE DAU TIENG VIET:
  LOG in ra GitHub Actions -> khong dau
  Tin nhan gui Telegram    -> tieng Viet co dau day du
"""
import os
import re
import sys
import json
import random
import time
from datetime import datetime, timedelta, timezone

import srs

VN = timezone(timedelta(hours=7))
TAB_TU_VUNG = "TuVung"
TAB_CAU_HINH = "CauHinh"
TAB_NHAT_KY = "NhatKyOn"

# Cot trong tab TuVung (1 = A)
C_STT, C_WORD, C_POS, C_IPA, C_NGHIA, C_NHOM, C_AUDIO = 1, 2, 3, 4, 5, 6, 7
C_VD1 = 8                 # H..O : VD1 Dich1 VD2 Dich2 VD3 Dich3 VD4 Dich4
C_TANG = 16               # P
C_ON_TIEP = 17            # Q
C_LAN_DAU = 18            # R
C_ON_CUOI = 19            # S
C_SO_NHO = 20             # T
C_SO_QUEN = 21            # U
C_TRANG_THAI = 22         # V
SO_CAU_VD = 4


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


def thoat_html(s):
    """Telegram parse_mode=HTML se tu choi ca tin neu co < > & chua thoat.
    Cau vi du hay chua & (vd 'the R&D department') -> bat buoc phai thoat."""
    return (str(s if s is not None else "")
            .replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;"))


# ------------------------------------------------------- chuyen ma phat am
def tai_va_chuyen_opus(url):
    """Tai file phat am roi chuyen sang OGG/Opus.

    VI SAO PHAI CHUYEN: Telegram chi dung "voice message" (cham la nghe ngay)
    khi file la OGG ma hoa bang OPUS. File cua Merriam-Webster la MP3, con ban
    .ogg cua ho ma hoa bang VORBIS - Telegram nhan nhung ha xuong thanh
    Document, phai tai ve moi nghe duoc.

    Tra ve bytes, hoac None neu that bai.
    """
    if not url:
        return None
    import subprocess
    import requests
    try:
        r = requests.get(url, timeout=25)
        if r.status_code != 200 or not r.content:
            return None
    except Exception as e:
        log("   Khong tai duoc phat am (%s)" % type(e).__name__)
        return None
    try:
        p = subprocess.run(
            ["ffmpeg", "-hide_banner", "-loglevel", "error",
             "-i", "pipe:0", "-c:a", "libopus", "-b:a", "32k",
             "-ar", "48000", "-ac", "1", "-f", "ogg", "pipe:1"],
            input=r.content, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            timeout=30)
    except Exception as e:
        log("   Khong chay duoc ffmpeg (%s)" % type(e).__name__)
        return None
    if p.returncode != 0 or not p.stdout:
        log("   ffmpeg loi: %s" % p.stderr.decode("utf-8", "ignore")[:120])
        return None
    return p.stdout


# ---------------------------------------------------------------- Telegram
class Telegram(object):
    def __init__(self, token, chat_id):
        import requests
        self.r = requests
        self.token = token
        self.chat_id = chat_id
        self.da_gui = 0

    def goi(self, method, body, im_lang=False):
        url = "https://api.telegram.org/bot%s/%s" % (self.token, method)
        try:
            r = self.r.post(url, json=body, timeout=30)
            kq = r.json()
        except Exception as e:
            log("   Loi mang khi goi %s: %s" % (method, type(e).__name__))
            return None
        if not kq.get("ok"):
            mo_ta = kq.get("description", "")
            if not im_lang:
                log("   Telegram tu choi %s: %s" % (method, mo_ta))
                if "chat not found" in mo_ta.lower():
                    log("   -> Chua bam Start cho bot, hoac TELEGRAM_CHAT_ID sai.")
                elif "can't parse entities" in mo_ta.lower():
                    log("   -> Noi dung con ky tu HTML chua thoat.")
                elif "message is not modified" in mo_ta.lower():
                    log("   -> Noi dung moi giong het cai cu, bo qua duoc.")
            return None
        self.da_gui += 1
        return kq["result"]

    def gui(self, text, nut=None, im_lang=False):
        body = {"chat_id": self.chat_id, "parse_mode": "HTML",
                "text": text, "disable_web_page_preview": True}
        if nut:
            body["reply_markup"] = {"inline_keyboard": nut}
        return self.goi("sendMessage", body, im_lang)

    def gui_voice(self, opus, caption, nut=None):
        """Gui MOT tin nhan duy nhat: voice message kem phan chu.
        Cham vao la nghe ngay, khong sinh them tin nhan nao."""
        url = "https://api.telegram.org/bot%s/sendVoice" % self.token
        data = {"chat_id": self.chat_id, "parse_mode": "HTML",
                "caption": caption[:1024]}
        if nut:
            data["reply_markup"] = json.dumps({"inline_keyboard": nut})
        try:
            r = self.r.post(url, data=data,
                            files={"voice": ("phatam.ogg", opus, "audio/ogg")},
                            timeout=60)
            kq = r.json()
        except Exception as e:
            log("   Loi mang khi gui voice: %s" % type(e).__name__)
            return None
        if not kq.get("ok"):
            log("   Telegram tu choi sendVoice: %s" % kq.get("description", ""))
            return None
        self.da_gui += 1
        return kq["result"]

    def gui_the(self, text, audio_url, nut=None):
        """Co phat am -> gui voice kem chu (1 tin). Khong co -> gui chu thuong."""
        if audio_url:
            opus = tai_va_chuyen_opus(audio_url)
            if opus:
                kq = self.gui_voice(opus, text, nut)
                if kq:
                    return kq, True
                log("   Gui voice that bai, lui ve tin nhan chu.")
        return self.gui(text, nut), False

    def gui_dai(self, text):
        """Telegram gioi han 4096 ky tu moi tin -> cat theo dong, khong cat giua chung."""
        gioi_han = 3800
        khoi, hien = [], ""
        for dong in text.split("\n"):
            if len(hien) + len(dong) + 1 > gioi_han:
                khoi.append(hien)
                hien = dong
            else:
                hien = (hien + "\n" + dong) if hien else dong
        if hien:
            khoi.append(hien)
        for k in khoi:
            self.gui(k)
            time.sleep(0.3)


# ---------------------------------------------------------------- Worker KV
class Worker(object):
    def __init__(self, base, secret):
        import requests
        self.r = requests
        self.base = (base or "").rstrip("/")
        self.secret = secret or ""
        self.bat = bool(self.base and self.secret)

    def _headers(self):
        return {"X-Bot-Secret": self.secret, "Content-Type": "application/json"}

    def luu_the(self, ds):
        if not self.bat or not ds:
            return False
        try:
            r = self.r.post(self.base + "/luu", headers=self._headers(),
                            json={"the": ds}, timeout=30)
            if r.status_code != 200:
                log("   /luu tra ve HTTP %d: %s" % (r.status_code, r.text[:120]))
                return False
            return True
        except Exception as e:
            log("   Loi khi goi /luu: %s" % type(e).__name__)
            return False

    def lay_phan_hoi(self):
        if not self.bat:
            return []
        try:
            r = self.r.get(self.base + "/phanhoi", headers=self._headers(), timeout=30)
            if r.status_code != 200:
                log("   /phanhoi tra ve HTTP %d" % r.status_code)
                return []
            return r.json().get("phan_hoi", [])
        except Exception as e:
            log("   Loi khi goi /phanhoi: %s" % type(e).__name__)
            return []

    def xoa(self, khoa):
        if not self.bat or not khoa:
            return
        try:
            self.r.post(self.base + "/xoa", headers=self._headers(),
                        json={"khoa": khoa}, timeout=30)
        except Exception as e:
            log("   Loi khi goi /xoa: %s" % type(e).__name__)


# ---------------------------------------------------------------- Sheets
def mo_sheet():
    sa_raw = os.environ.get("GOOGLE_SA_JSON", "")
    sheet_id = os.environ.get("SHEET_ID", "")
    if not sheet_id:
        die("Bien SHEET_ID chua toi duoc script.")
    if not sa_raw:
        die("Bien GOOGLE_SA_JSON chua toi duoc script.")
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
        return gc.open_by_key(sheet_id)
    except Exception as e:
        die("Khong mo duoc Google Sheet: %s" % e,
            "Chay lai workflow 'Test ket noi Google Sheets' de khoanh vung loi.")


def doc_cau_hinh(sh):
    cfg = {}
    try:
        for hang in sh.worksheet(TAB_CAU_HINH).get_all_values()[1:]:
            if len(hang) >= 2 and hang[0].strip():
                cfg[hang[0].strip()] = hang[1].strip()
    except Exception as e:
        log("Khong doc duoc tab CauHinh (%s), dung gia tri mac dinh." % e)
    return cfg


def cfg_so(cfg, ten, mac_dinh):
    try:
        return int(str(cfg.get(ten, mac_dinh)).strip())
    except Exception:
        return mac_dinh


def doc_the(ws):
    """Doc tab TuVung thanh danh sach The, kem du lieu hien thi."""
    tat_ca = ws.get_all_values()
    cac_the, thong_tin = [], {}
    for i, hang in enumerate(tat_ca[1:], start=2):
        def o(c):
            return hang[c - 1].strip() if len(hang) >= c else ""
        word = o(C_WORD)
        if not word:
            continue
        t = srs.The(
            dong=i, word=word, nhom=o(C_NHOM) or "A",
            tang=cfg_int(o(C_TANG)), ngay_on_tiep=srs.doc_ngay(o(C_ON_TIEP)),
            lan_dau_gui=srs.doc_ngay(o(C_LAN_DAU)), lan_on_cuoi=srs.doc_ngay(o(C_ON_CUOI)),
            so_nho=cfg_int(o(C_SO_NHO)), so_quen=cfg_int(o(C_SO_QUEN)),
            trang_thai=o(C_TRANG_THAI) or srs.CHUA_GUI,
        )
        vd = []
        for k in range(SO_CAU_VD):
            en, vi = o(C_VD1 + k * 2), o(C_VD1 + k * 2 + 1)
            if en and vi:
                vd.append((en, vi))
        thong_tin[i] = {
            "pos": o(C_POS), "ipa": o(C_IPA) or "", "nghia": o(C_NGHIA),
            "audio": o(C_AUDIO) if o(C_AUDIO) not in ("", "-") else "",
            "vd": vd,
        }
        cac_the.append(t)
    return cac_the, thong_tin


def cfg_int(s):
    try:
        return int(float(str(s).strip()))
    except Exception:
        return 0


def ghi_the(ws, cac_the):
    """Ghi cot P..V cho cac the thay doi. Gom thanh khoi lien tiep de it request."""
    if not cac_the:
        return
    theo_dong = {t.dong: t for t in cac_the}
    ds = sorted(theo_dong)
    khoi, dau, truoc = [], ds[0], ds[0]
    for d in ds[1:]:
        if d == truoc + 1:
            truoc = d
        else:
            khoi.append((dau, truoc))
            dau = truoc = d
    khoi.append((dau, truoc))
    yeu_cau = []
    for a, b in khoi:
        gia_tri = []
        for d in range(a, b + 1):
            t = theo_dong[d]
            gia_tri.append([t.tang, srs.ghi_ngay(t.ngay_on_tiep),
                            srs.ghi_ngay(t.lan_dau_gui), srs.ghi_ngay(t.lan_on_cuoi),
                            t.so_nho, t.so_quen, t.trang_thai])
        yeu_cau.append({"range": "P%d:V%d" % (a, b), "values": gia_tri})
    for i in range(0, len(yeu_cau), 100):
        ws.batch_update(yeu_cau[i:i + 100], value_input_option="RAW")


# ---------------------------------------------------------------- soan tin
def chon_cau_vd(vd, tang):
    """Moi lan on dung mot cau khac. Tu tang 5 tro di thi quay vong lai."""
    if not vd:
        return None
    return vd[max(0, tang - 1) % len(vd)]


def mat_truoc(the, tt, tang, tong, thu_tu):
    """Man on tap: chi hien TU, chua hien nghia -> ep nho lai, khong phai nhan ra."""
    cau = chon_cau_vd(tt["vd"], tang)
    dong = ["🔁 <b>Ôn tập</b>  <i>%d/%d</i>  ·  tầng %d" % (thu_tu, tong, tang), ""]
    dong.append("<b>%s</b>" % thoat_html(the.word))
    if tt["ipa"]:
        dong.append("<code>%s</code>" % thoat_html(tt["ipa"]))
    if cau:
        che = re.sub(r"(?<!\w)" + re.escape(the.word) + r"(?!\w)", "______",
                     cau[0], flags=re.IGNORECASE)
        dong += ["", thoat_html(che)]
    return "\n".join(dong)


def mat_sau(the, tt, tang):
    cau = chon_cau_vd(tt["vd"], tang)
    dong = ["🔁 <b>Ôn tập</b>  ·  tầng %d" % tang, ""]
    dau = "<b>%s</b>" % thoat_html(the.word)
    if tt["pos"]:
        dau += "  <i>(%s)</i>" % thoat_html(tt["pos"])
    dong.append(dau)
    if tt["ipa"]:
        dong.append("<code>%s</code>" % thoat_html(tt["ipa"]))
    dong.append("→ %s" % thoat_html(tt["nghia"]))
    if cau:
        dong += ["", thoat_html(cau[0]), "→ %s" % thoat_html(cau[1])]
    return "\n".join(dong)


def tin_tu_moi(the, tt, thu_tu, tong):
    cau = tt["vd"][0] if tt["vd"] else None
    dong = ["📖 <b>Từ mới</b>  <i>%d/%d</i>" % (thu_tu, tong), ""]
    dau = "<b>%s</b>" % thoat_html(the.word)
    if tt["pos"]:
        dau += "  <i>(%s)</i>" % thoat_html(tt["pos"])
    dong.append(dau)
    if tt["ipa"]:
        dong.append("<code>%s</code>" % thoat_html(tt["ipa"]))
    dong.append("→ %s" % thoat_html(tt["nghia"]))
    if cau:
        dong += ["", thoat_html(cau[0]), "→ %s" % thoat_html(cau[1])]
    return "\n".join(dong)


# Khong con nut "Nghe": file phat am duoc gan thang vao tin nhan the,
# cham vao la nghe ngay, khong sinh tin nhan phu.
def nut_on_tap(dong, co_audio=False):
    return [[{"text": "👁 Xem nghĩa", "callback_data": "x:%d" % dong}]]


def nut_tu_moi(dong, co_audio=False):
    return [[{"text": "⏭ Đã biết rồi", "callback_data": "b:%d" % dong}]]


# ---------------------------------------------------------------- dong bo
def dong_bo_phan_hoi(ws, cac_the, worker, lich, hom_nay):
    """Doc phan hoi nguoi dung da bam tu KV, ap vao the, ghi nguoc vao Sheet."""
    ds = worker.lay_phan_hoi()
    if not ds:
        log("Dong bo phan hoi: khong co gi moi.")
        return [], []
    theo_dong = {t.dong: t for t in cac_the}
    ds.sort(key=lambda p: p.get("luc", ""))     # ap theo dung thu tu thoi gian
    da_doi, khoa_xong, nhat_ky = {}, [], []
    bo_qua = 0
    for p in ds:
        t = theo_dong.get(p.get("dong"))
        if not t:
            bo_qua += 1
            khoa_xong.append(p["khoa"])
            continue
        truoc = t.tang
        hd = p.get("hanh_dong")
        if hd == "nho":
            lich.tra_loi_nho(t, hom_nay)
        elif hd == "quen":
            lich.tra_loi_quen(t, hom_nay)
        elif hd == "hoan":
            lich.tra_loi_de_sau(t, hom_nay)
        elif hd == "da_biet":
            lich.danh_dau_da_biet(t, hom_nay)
        else:
            bo_qua += 1
            khoa_xong.append(p["khoa"])
            continue
        da_doi[t.dong] = t
        khoa_xong.append(p["khoa"])
        nhat_ky.append([p.get("luc", "")[:19].replace("T", " "), t.dong, t.word,
                        truoc, hd, t.tang, srs.ghi_ngay(t.ngay_on_tiep)])
    log("Dong bo phan hoi: %d muc, ap duoc %d, bo qua %d."
        % (len(ds), len(da_doi), bo_qua))
    return list(da_doi.values()), (khoa_xong, nhat_ky)


# ---------------------------------------------------------------- cac che do
def gui_tu_moi(tg, worker, ws, cac_the, thong_tin, lich, hom_nay, so_luong,
               ngay_thi, nguong, them=False):
    kh = srs.ke_hoach_ngay(cac_the, hom_nay, so_luong, ngay_thi, nguong,
                           rng=random.Random(), tran_on=0)
    if kh["nuoc_rut"] and not them:
        log("Dang nuoc rut (con %d ngay) -> khong nap tu moi."
            % kh["con_lai_den_ngay_thi"])
        return []
    ds = kh["tu_moi"]
    if not ds:
        tg.gui("📖 Kho từ đã hết. Không còn từ mới để gửi.")
        return []

    con = srs.so_ngay_con_lai(hom_nay, ngay_thi)
    tieu_de = "📖 <b>%d TỪ MỚI HÔM NAY</b>" % len(ds)
    if con is not None:
        tieu_de += "\n<i>Còn %d ngày đến kỳ thi</i>" % con
    tg.gui(tieu_de)

    luu = []
    for i, t in enumerate(ds, start=1):
        tt = thong_tin[t.dong]
        kq, la_voice = tg.gui_the(tin_tu_moi(t, tt, i, len(ds)), tt["audio"],
                                  nut_tu_moi(t.dong))
        if kq:
            luu.append({"message_id": kq["message_id"], "dong": t.dong,
                        "word": t.word, "mat_sau": "", "audio": tt["audio"],
                        "la_voice": la_voice})
        lich.gui_lan_dau(t, hom_nay)
        time.sleep(0.4)
    worker.luu_the(luu)
    log("Da gui %d tu moi." % len(ds))
    return ds


def gui_on_tap(tg, worker, cac_the, thong_tin, hom_nay, ngay_thi, nguong, tran):
    kh = srs.ke_hoach_ngay(cac_the, hom_nay, 0, ngay_thi, nguong, tran_on=tran)
    ds = kh["on_tap"]
    if not ds:
        log("Khong co the nao den han on.")
        return []
    dau = "🔁 <b>ÔN TẬP — %d từ</b>" % len(ds)
    if kh["ton_lai"]:
        dau += ("\n<i>Còn %d từ chưa tới lượt, sẽ đưa dần vào các ngày tới.</i>"
                % kh["ton_lai"])
    tg.gui(dau)

    luu = []
    for i, t in enumerate(ds, start=1):
        tt = thong_tin[t.dong]
        kq, la_voice = tg.gui_the(mat_truoc(t, tt, t.tang, len(ds), i),
                                  tt["audio"], nut_on_tap(t.dong))
        if kq:
            luu.append({"message_id": kq["message_id"], "dong": t.dong,
                        "word": t.word, "mat_sau": mat_sau(t, tt, t.tang),
                        "audio": tt["audio"], "la_voice": la_voice})
        time.sleep(0.4)
    if not worker.luu_the(luu):
        log("CANH BAO: khong luu duoc mat sau vao KV -> nut 'Xem nghia' se bao het han.")
    log("Da gui %d the on tap." % len(ds))
    return ds


def gui_thong_ke(tg, cac_the, thong_tin, hom_nay, lich, ngay_thi):
    tk = srs.thong_ke(cac_the, hom_nay, lich)
    bat_dau = min([t.lan_dau_gui for t in cac_the if t.lan_dau_gui] or [hom_nay])
    ngay_thu = (hom_nay - bat_dau).days + 1
    con = srs.so_ngay_con_lai(hom_nay, ngay_thi)

    d = ["📊 <b>THỐNG KÊ HỌC TẬP</b>", ""]
    d.append("Bắt đầu: %s  (ngày thứ %d)" % (bat_dau.strftime("%d/%m/%Y"), ngay_thu))
    if con is not None:
        d.append("Còn <b>%d ngày</b> đến kỳ thi" % con)
    d += ["", "Đã tiếp xúc: <b>%d</b> / %d từ"
          % (tk["tong_kho"] - tk["chua_gui"], tk["tong_kho"])]
    d.append("├ Thuộc:        %d" % tk["thuoc"])
    d.append("├ Đang học:     %d" % tk["dang_hoc"])
    d.append("└ Đã biết sẵn:  %d" % tk["da_biet"])
    if tk["theo_tang"]:
        d += ["", "<b>Phân bố theo tầng</b>"]
        for tang in sorted(tk["theo_tang"]):
            kc = lich.khoang_cach(tang)
            d.append("  tầng %d (ôn mỗi %d ngày): %d từ"
                     % (tang, kc, tk["theo_tang"][tang]))
    if tk["tong_luot_on"]:
        d += ["", "Tỷ lệ nhớ: <b>%.0f%%</b>  (%d lượt ôn)"
              % (tk["ty_le_nho"], tk["tong_luot_on"])]
    if tk["den_han_hom_nay"]:
        d.append("Đến hạn hôm nay: %d từ" % tk["den_han_hom_nay"])
    if tk["tu_cung_dau"]:
        d += ["", "<b>Từ cứng đầu</b> (quên từ 3 lần trở lên)"]
        for t in tk["tu_cung_dau"]:
            tt = thong_tin.get(t.dong, {})
            d.append("  • %s — %s  <i>(quên %d lần)</i>"
                     % (thoat_html(t.word), thoat_html(tt.get("nghia", "")), t.so_quen))
    con_kho = tk["chua_gui"]
    if con_kho:
        d += ["", "Kho còn lại: %d từ" % con_kho]
    tg.gui_dai("\n".join(d))


def tra_tu(tg, cac_the, thong_tin, tu_can_tra, lich):
    tu = (tu_can_tra or "").strip().lower()
    if not tu:
        tg.gui("Cú pháp: <code>/tim từ_cần_tra</code>")
        return
    khop = [t for t in cac_the if t.word.lower() == tu]
    if not khop:
        khop = [t for t in cac_the if tu in t.word.lower()][:5]
    if not khop:
        tg.gui("Không tìm thấy “%s” trong kho từ." % thoat_html(tu_can_tra))
        return
    for t in khop[:3]:
        tt = thong_tin[t.dong]
        d = ["🔎 <b>%s</b>" % thoat_html(t.word)]
        if tt["ipa"]:
            d.append("<code>%s</code>" % thoat_html(tt["ipa"]))
        d.append("→ %s" % thoat_html(tt["nghia"]))
        d.append("")
        if t.trang_thai == srs.CHUA_GUI:
            d.append("<i>Chưa học từ này.</i>")
        else:
            nhan = {srs.THUOC: "Đã thuộc", srs.DA_BIET: "Đánh dấu đã biết",
                    srs.DANG_HOC: "Đang học — tầng %d" % t.tang}.get(t.trang_thai, t.trang_thai)
            d.append("Trạng thái: <b>%s</b>" % nhan)
            if t.ngay_on_tiep:
                d.append("Ôn tiếp: %s" % t.ngay_on_tiep.strftime("%d/%m/%Y"))
            d.append("Nhớ %d lần · quên %d lần" % (t.so_nho, t.so_quen))
        for en, vi in tt["vd"][:2]:
            d += ["", thoat_html(en), "→ %s" % thoat_html(vi)]
        tg.gui("\n".join(d))


# ---------------------------------------------------------------- main
def main():
    viec = (os.environ.get("VIEC") or "dong_bo").strip()
    tham_so = (os.environ.get("THAM_SO") or "").strip()
    token = (os.environ.get("TELEGRAM_TOKEN") or "").strip()
    chat_id = (os.environ.get("TELEGRAM_CHAT_ID") or "").strip()
    worker_url = (os.environ.get("WORKER_URL") or "").strip()
    bot_secret = (os.environ.get("BOT_SECRET") or "").strip()

    hom_nay = datetime.now(VN).date()

    log("=" * 62)
    log("CAU HINH DANG DUNG")
    log("=" * 62)
    log("VIEC             : " + viec)
    log("THAM_SO          : " + (tham_so or "(trong)"))
    log("Hom nay (gio VN) : " + hom_nay.isoformat())
    log("TELEGRAM_TOKEN   : " + ("co, %d ky tu" % len(token) if token else "(TRONG)"))
    log("TELEGRAM_CHAT_ID : " + (chat_id or "(TRONG)"))
    log("WORKER_URL       : " + (worker_url or "(TRONG - nut bam se khong hoat dong)"))
    log("BOT_SECRET       : " + ("co, %d ky tu" % len(bot_secret) if bot_secret else "(TRONG)"))
    log("")

    if not token or not chat_id:
        die("Thieu TELEGRAM_TOKEN hoac TELEGRAM_CHAT_ID.",
            "Tao secret trong repo: Settings > Secrets and variables > Actions.")

    sh = mo_sheet()
    cfg = doc_cau_hinh(sh)
    ws = sh.worksheet(TAB_TU_VUNG)

    tang_str = cfg.get("TANG_LEITNER", "1,3,7,16,35,70")
    try:
        cac_tang = [int(x) for x in tang_str.split(",") if x.strip()]
    except Exception:
        cac_tang = srs.TANG_MAC_DINH
    lich = srs.LichHoc(cac_tang)
    so_tu_moi = cfg_so(cfg, "SO_TU_MOI_MOI_NGAY", 5)
    nguong = cfg_so(cfg, "NUOC_RUT_TRUOC_NGAY", 21)
    tran_on = cfg_so(cfg, "TRAN_ON_MOI_NGAY", 45)
    ngay_thi = srs.doc_ngay(cfg.get("NGAY_THI", ""))

    log("Bac thang     : %s" % cac_tang)
    log("Tu moi/ngay   : %d" % so_tu_moi)
    log("Tran on/ngay  : %d" % tran_on)
    log("Ngay thi      : %s" % (srs.ghi_ngay(ngay_thi) or "(chua dat)"))
    log("")

    cac_the, thong_tin = doc_the(ws)
    log("Doc %d the tu tab %s." % (len(cac_the), TAB_TU_VUNG))

    tg = Telegram(token, chat_id)
    worker = Worker(worker_url, bot_secret)
    if not worker.bat:
        log("CANH BAO: chua co WORKER_URL/BOT_SECRET -> khong dong bo duoc nut bam.")

    # --- Luon dong bo phan hoi truoc, du dang lam viec gi ---
    da_doi, kem = dong_bo_phan_hoi(ws, cac_the, worker, lich, hom_nay)
    if da_doi:
        ghi_the(ws, da_doi)
        khoa_xong, nhat_ky = kem
        if nhat_ky:
            try:
                sh.worksheet(TAB_NHAT_KY).append_rows(nhat_ky, value_input_option="RAW")
            except Exception as e:
                log("   Khong ghi duoc NhatKyOn (%s) - bo qua, khong quan trong." % e)
        worker.xoa(khoa_xong)
        log("Da ghi %d the va xoa %d phan hoi khoi KV." % (len(da_doi), len(khoa_xong)))

    # --- Thuc hien viec duoc yeu cau ---
    moi_gui = []
    if viec in ("tu_moi", "tu_moi_them"):
        moi_gui = gui_tu_moi(tg, worker, ws, cac_the, thong_tin, lich, hom_nay,
                             so_tu_moi, ngay_thi, nguong,
                             them=(viec == "tu_moi_them"))
        if moi_gui:
            ghi_the(ws, moi_gui)
    elif viec == "on_tap":
        gui_on_tap(tg, worker, cac_the, thong_tin, hom_nay, ngay_thi, nguong, tran_on)
    elif viec == "thong_ke":
        gui_thong_ke(tg, cac_the, thong_tin, hom_nay, lich, ngay_thi)
    elif viec == "tra_tu":
        tra_tu(tg, cac_the, thong_tin, tham_so, lich)
    elif viec == "dong_bo":
        pass
    elif viec in ("toeic_de", "toeic_da"):
        # Chua co ngan hang cau -> bao ro, khong im lang de nguoi dung khoi cho.
        log("Viec '%s' chua duoc cai dat (chua co ngan hang cau TOEIC)." % viec)
        if viec == "toeic_de":
            tg.gui("🚧 Phần luyện đề TOEIC chưa dựng xong.\n"
                   "Hiện bot mới chạy phần từ vựng.")
    else:
        log("Viec '%s' khong nhan ra, bo qua." % viec)

    log("")
    log("=" * 62)
    log("XONG. Da gui %d tin nhan Telegram." % tg.da_gui)
    log("=" * 62)


if __name__ == "__main__":
    main()
