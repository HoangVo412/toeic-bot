# -*- coding: utf-8 -*-
"""
gen_cauhoi.py — Sinh ngan hang cau hoi NGU PHAP TOEIC Part 5 va Part 6.

Quy trinh:
    Model A sinh cau  ->  lop kiem co hoc  ->  Model B giai MU (khong thay dap an)
    -> dong thuan: DA_DUYET  |  bat dong: XUNG_DOT (nguoi dung duyet tay)

Chay tay qua GitHub Actions (workflow_dispatch). Khong co tuong tac nguoi dung
nen dat o Actions la dung cho — xem muc 2.1 PROJECT-TOEIC-BOT.md.

Bien moi truong bat buoc:
    GEMINI_KEY, GOOGLE_SA_JSON, SHEET_ID
Bien tuy chon (inputs cua workflow):
    SO_CAU_P5   (mac dinh 40)
    SO_DOAN_P6  (mac dinh 5)
    CHI_DANG    (rong = tat ca; hoac ma dang, vd TU_LOAI)
    KHO_HON     ("true" = yeu cau do kho cao hon)
"""

import calendar
import json
import os
import random
import re
import sys
import time
from datetime import datetime, timedelta, timezone

import requests

import cauhoi_config as CFG

VN_TZ = timezone(timedelta(hours=7))


def log(*a):
    """Log KHONG DAU — tranh loi encoding tren runner."""
    print(*a, flush=True)


def now_vn():
    return datetime.now(VN_TZ)


# ===========================================================================
# 0. CAU HINH TU MOI TRUONG
# ===========================================================================
GEMINI_KEY = os.environ.get("GEMINI_KEY", "").strip()
SHEET_ID = os.environ.get("SHEET_ID", "").strip()
SA_JSON = os.environ.get("GOOGLE_SA_JSON", "").strip()

SO_CAU_P5 = int(os.environ.get("SO_CAU_P5") or 40)
SO_DOAN_P6 = int(os.environ.get("SO_DOAN_P6") or 5)
CHI_DANG = (os.environ.get("CHI_DANG") or "").strip().upper()
KHO_HON = (os.environ.get("KHO_HON") or "").lower() == "true"
EP_MODEL_KIEM = (os.environ.get("MODEL_KIEM") or "").strip()

LO_P5 = 6      # so cau moi lan goi Gemini (Part 5)
LO_P6 = 2      # so doan moi lan goi Gemini (Part 6)
LO_KIEM = 12   # so cau moi lan goi Model B (dau ra ~60 token/cau, xa tran)


def kiem_cau_hinh():
    thieu = [t for t, v in [("GEMINI_KEY", GEMINI_KEY), ("SHEET_ID", SHEET_ID),
                            ("GOOGLE_SA_JSON", SA_JSON)] if not v]
    if thieu:
        log("LOI: thieu bien moi truong:", ", ".join(thieu))
        sys.exit(1)
    log(f"Cau hinh | SHEET_ID={SHEET_ID[:12]}... | GEMINI_KEY: co, {len(GEMINI_KEY)} ky tu"
        f" | SA_JSON: co, {len(SA_JSON)} ky tu")
    log(f"Yeu cau  | Part5={SO_CAU_P5} cau | Part6={SO_DOAN_P6} doan"
        f" | chi_dang={CHI_DANG or '(tat ca)'} | kho_hon={KHO_HON}")
    log(f"Model kiem ep buoc: {EP_MODEL_KIEM or '(tu chon)'}")


# ===========================================================================
# 1. GEMINI — tu do model, dieu tiet nhip, phan biet RPM voi RPD
# ===========================================================================
API = "https://generativelanguage.googleapis.com/v1beta"

# HAI VAI, HAI TIEU CHI CHON MODEL KHAC NHAU:
#   SINH  = viec chay hang loat -> chon theo HAN MUC (Lite, RPD 500) — muc 3.5
#   KIEM  = viec it luot goi   -> chon theo CHAT LUONG (model manh nhat)
# 60 cau chia lo 12 chi het 5 luot kiem, RPD 20 cua ban manh thua suc.
TEN_SINH = [
    "gemini-3.5-flash-lite", "gemini-3.1-flash-lite",
    "gemini-flash-lite-latest", "gemini-2.5-flash-lite",
]
TEN_KIEM = [
    "gemini-flash-latest", "gemini-3.5-flash", "gemini-3-flash",
    "gemini-2.5-flash",
]

RPM_MAC_DINH = {"lite": 15, "khac": 5}
_lan_goi_cuoi = {}
_so_429 = {}


def _rpm(model):
    return RPM_MAC_DINH["lite"] if "lite" in model else RPM_MAC_DINH["khac"]


def _cho_nhip(model):
    """Cho du 60/RPM giay ke tu lan goi truoc CUNG model."""
    cho = 60.0 / _rpm(model)
    truoc = _lan_goi_cuoi.get(model)
    if truoc:
        con = cho - (time.time() - truoc)
        if con > 0:
            time.sleep(con)
    _lan_goi_cuoi[model] = time.time()


def goi_gemini(model, prompt, max_tokens=8192, nhiet=0.85):
    """Tra ve (text, ly_do_ket_thuc) hoac (None, ma_loi)."""
    _cho_nhip(model)
    url = f"{API}/models/{model}:generateContent?key={GEMINI_KEY}"
    body = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {
            "temperature": nhiet,
            "maxOutputTokens": max_tokens,
            "responseMimeType": "application/json",
        },
    }
    try:
        r = requests.post(url, json=body, timeout=180)
    except requests.RequestException as e:
        return None, f"MANG:{type(e).__name__}"

    if r.status_code == 429:
        _so_429[model] = _so_429.get(model, 0) + 1
        return None, "429"
    if r.status_code == 404:
        return None, "404"
    if r.status_code != 200:
        return None, f"HTTP{r.status_code}:{r.text[:120]}"

    try:
        d = r.json()
        cand = d["candidates"][0]
        ly_do = cand.get("finishReason", "")
        txt = "".join(p.get("text", "") for p in cand["content"]["parts"])
        return txt, ly_do
    except (KeyError, IndexError, ValueError):
        return None, f"PHANHOI_LA:{r.text[:120]}"


def chon_model(danh_sach, can=2, uu_tien_lite=True):
    """Xac thuc model chay duoc trong danh_sach. Tu do tu API neu ten cung hong."""
    ok = []
    for m in danh_sach:
        txt, ly = goi_gemini(m, 'Tra ve dung JSON: {"ok":1}', max_tokens=64, nhiet=0)
        if txt:
            ok.append(m)
            log(f"  model OK   : {m}")
        else:
            log(f"  model hong : {m} -> {ly}")
        if len(ok) >= can:
            break

    if len(ok) >= can:
        return ok

    log("Ten cung khong du -> tu do danh sach model that tu API.")
    try:
        r = requests.get(f"{API}/models?key={GEMINI_KEY}&pageSize=200", timeout=60)
        ds = [m["name"].split("/")[-1] for m in r.json().get("models", [])
              if "generateContent" in m.get("supportedGenerationMethods", [])]
    except Exception as e:
        log("  khong do duoc:", e)
        ds = []
    # Uu tien lite, bo cac ban preview/exp/thinking cho on dinh
    ds.sort(key=lambda n: ((0 if "lite" in n else 1) if uu_tien_lite
                           else (0 if "lite" not in n else 1),
                           1 if any(k in n for k in ("exp", "preview", "thinking")) else 0,
                           n))
    log("  API tra ve:", ", ".join(ds[:12]) or "(rong)")
    for m in ds:
        if m in ok:
            continue
        txt, ly = goi_gemini(m, 'Tra ve dung JSON: {"ok":1}', max_tokens=64, nhiet=0)
        if txt:
            ok.append(m)
            log(f"  model OK   : {m}")
        if len(ok) >= can:
            break

    if not ok:
        log("LOI: khong model nao chay duoc. Kiem tra GEMINI_KEY.")
        sys.exit(1)
    return ok


# ===========================================================================
# 2. PHAN TICH JSON — va truong hop bi cat giua chung (muc 3.7)
# ===========================================================================
def _boc_rao(t):
    t = t.strip()
    t = re.sub(r"^```(?:json)?\s*", "", t)
    t = re.sub(r"\s*```$", "", t)
    return t.strip()


def doc_json_list(txt):
    """Tra ve list cac dict. Neu JSON bi cat, vot cac object can bang ngoac."""
    txt = _boc_rao(txt)
    try:
        d = json.loads(txt)
        if isinstance(d, list):
            return d
        if isinstance(d, dict):
            for k in ("cau", "cau_hoi", "items", "data", "doan", "ket_qua"):
                if isinstance(d.get(k), list):
                    return d[k]
            return [d]
    except ValueError:
        pass

    # Vot thu cong: quet tim cac object {...} can bang ngoac, bo qua ngoac
    # nam trong chuoi.
    ra, sau, trong_chuoi, thoat, bd = [], 0, False, False, None
    for i, c in enumerate(txt):
        if trong_chuoi:
            if thoat:
                thoat = False
            elif c == "\\":
                thoat = True
            elif c == '"':
                trong_chuoi = False
            continue
        if c == '"':
            trong_chuoi = True
        elif c == "{":
            if sau == 0:
                bd = i
            sau += 1
        elif c == "}":
            sau -= 1
            if sau == 0 and bd is not None:
                try:
                    ra.append(json.loads(txt[bd:i + 1]))
                except ValueError:
                    pass
                bd = None
    if ra:
        log(f"    (JSON bi cat, vot duoc {len(ra)} object)")
    return ra


# ===========================================================================
# 3. PROMPT
# ===========================================================================
LUAT_CHUNG = """QUY TAC BAT BUOC:
- Cau tieng Anh dung van phong cong so trang trong, dung khong khi de TOEIC that.
- KHONG dung ten rieng co that, khong dung ten cong ty co that.
- Cho trong ky hieu bang dung 4 dau gach duoi: ____
- Moi cau CHI co DUNG MOT cho trong.
- Ba dap an sai phai SAI RO RANG ve ngu phap, khong duoc cung chap nhan duoc.
- Vi tri dap an dung phai rai deu, khong tap trung mot chu cai.
- Giai thich viet bang TIENG VIET CO DAU, neu ro QUY TAC ngu phap, khong dien giai chung chung.
- Truong "vi_sao_sai" neu ngan gon vi sao TUNG dap an sai la sai.
- Tra ve DUNG mot mang JSON, khong loi dan, khong rao ```."""


def prompt_p5(dang, so_cau, boi_canh):
    d = CFG.DANG[dang]
    kho = ("Do kho: cao — them thanh phan xen giua chu ngu va dong tu, "
           "hoac dung cau truc it gap.") if KHO_HON else \
          "Do kho: trung binh, ngang de TOEIC chinh thuc."
    return f"""Ban la nguoi ra de TOEIC Part 5 (Incomplete Sentences).

Sinh {so_cau} cau hoi ngu phap dang "{d['ten']}".
Dac diem dang nay: {d['goi_y']}
{kho}
Boi canh cac cau: {boi_canh}

{LUAT_CHUNG}

Dinh dang moi phan tu:
{{"cau":"The manager ____ the report before the deadline.",
 "a":"submit","b":"submits","c":"submitted","d":"submitting",
 "dung":"C",
 "giai_thich":"Trang ngu 'before the deadline' cung voi ngu canh da hoan tat yeu cau thi qua khu don.",
 "vi_sao_sai":"A: thieu chia thi. B: hien tai don khong hop moc thoi gian. D: V-ing khong lam dong tu chinh.",
 "do_kho":2}}"""


def prompt_p6(so_doan, boi_canh):
    dangs = ", ".join(f"{k} ({CFG.DANG[k]['ten']})" for k in CFG.TY_LE_PART6)
    return f"""Ban la nguoi ra de TOEIC Part 6 (Text Completion).

Sinh {so_doan} doan van, moi doan {CFG.SO_TU_TOI_THIEU_DOAN}-{CFG.SO_TU_TOI_DA_DOAN} tu,
dang email cong ty / thong bao / quang cao. Boi canh: {boi_canh}

Moi doan co DUNG 4 cho trong, danh dau trong doan bang (1) (2) (3) (4).
Bon cho trong phai thuoc bon dang: {dangs}
Cho trong dang TU_NOI PHAI phu thuoc quan he logic voi cau LIEN TRUOC —
doc rieng cau chua cho trong thi khong the chon dung.

{LUAT_CHUNG}
(Rieng Part 6: cho trong trong doan dung (1)(2)(3)(4), truong "cau" la
cau chua cho trong tach rieng ra, van dung ____ )

Dinh dang moi phan tu:
{{"doan":"Dear staff, the elevator in Building B will be out of service next week. (1) ____, please use the east stairwell. We (2) ____ the maintenance work by Friday. ...",
 "cho_trong":[
   {{"so":1,"dang":"TU_NOI","cau":"____, please use the east stairwell.",
     "a":"However","b":"In the meantime","c":"For example","d":"Similarly","dung":"B",
     "giai_thich":"...","vi_sao_sai":"...","do_kho":2}},
   {{"so":2,"dang":"THI","cau":"We ____ the maintenance work by Friday.", ...}}
 ]}}"""


def prompt_kiem(cau_list):
    ds = []
    for c in cau_list:
        khoi = (f'{{"ma":"{c["ma"]}"' +
                (f',"doan":{json.dumps(c["doan"], ensure_ascii=False)}' if c.get("doan") else "") +
                f',"cau":{json.dumps(c["cau"], ensure_ascii=False)}' +
                f',"a":{json.dumps(c["a"], ensure_ascii=False)}' +
                f',"b":{json.dumps(c["b"], ensure_ascii=False)}' +
                f',"c":{json.dumps(c["c"], ensure_ascii=False)}' +
                f',"d":{json.dumps(c["d"], ensure_ascii=False)}}}')
        ds.append(khoi)
    return f"""Ban la giam khao kiem dinh de TOEIC. Duoi day la cac cau hoi Part 5-6.
Ban KHONG duoc biet dap an chuan. Hay tu giai tung cau.

Voi MOI cau, tra ve:
- "chon": chu cai dap an dung NHAT (A/B/C/D)
- "nhieu_dap_an": true neu co tu hai dap an tro len deu dung ngu phap va hop
  ngu canh; false neu chi mot dap an dung
- "loi_de": true neu cau bi loi (thieu cho trong, cau khong tu nhien, dap an
  trung nhau, khong dap an nao dung); false neu de on
- "ly_do": mot cau ngan bang TIENG VIET CO DAU

Nghiem khac. Neu con ngo vuc thi dat "nhieu_dap_an" hoac "loi_de" = true.
Tra ve DUNG mot mang JSON, khong loi dan, khong rao ```.

Cac cau:
[{",".join(ds)}]

Dinh dang tra ve: {{"ma":"...","chon":"B","nhieu_dap_an":false,"loi_de":false,"ly_do":"..."}}"""


# ===========================================================================
# 4. LOP KIEM CO HOC
# ===========================================================================
_RE_TRONG = re.compile(r"_{3,}")


def _chuan(s):
    return re.sub(r"\s+", " ", str(s or "")).strip()


def _co_dau_viet(s):
    return bool(re.search(r"[àáảãạăằắẳẵặâầấẩẫậèéẻẽẹêềếểễệìíỉĩị"
                          r"òóỏõọôồốổỗộơờớởỡợùúủũụưừứửữựỳýỷỹỵđ]", s, re.I))


def _goc(tu):
    """Lay 4 ky tu dau cua tu dai nhat trong lua chon, chuan hoa y -> i."""
    toks = re.findall(r"[A-Za-z]+", tu)
    if not toks:
        return ""
    dai = max(toks, key=len).lower()
    dai = re.sub(r"y$", "i", dai)
    return dai[:4]


def kiem_co_hoc(c):
    """Tra ve list loi (rong = dat)."""
    loi = []
    dang = c["dang"]
    d = CFG.DANG.get(dang)
    if not d:
        return [f"dang la: {dang}"]

    cau = _chuan(c["cau"])
    cau = _RE_TRONG.sub("____", cau)
    c["cau"] = cau

    n_trong = cau.count("____")
    if n_trong != 1:
        loi.append(f"co {n_trong} cho trong, phai la 1")

    if _co_dau_viet(cau):
        loi.append("cau tieng Anh lai chu co dau tieng Viet")

    so_tu = len(cau.replace("____", " ").split())
    if c["part"] == 5 and not (CFG.SO_TU_TOI_THIEU_P5 <= so_tu <= CFG.SO_TU_TOI_DA_P5):
        loi.append(f"do dai {so_tu} tu, ngoai khoang "
                   f"{CFG.SO_TU_TOI_THIEU_P5}-{CFG.SO_TU_TOI_DA_P5}")

    lua = [_chuan(c[k]) for k in ("a", "b", "c", "d")]
    if any(not x for x in lua):
        loi.append("co lua chon rong")
    thuong = [x.lower() for x in lua]
    if len(set(thuong)) != 4:
        loi.append("lua chon trung nhau")
    for k, v in zip(("a", "b", "c", "d"), lua):
        c[k] = v

    if str(c.get("dung", "")).upper() not in ("A", "B", "C", "D"):
        loi.append(f"dap an dung khong hop le: {c.get('dung')}")
    c["dung"] = str(c.get("dung", "")).upper()

    # Tap dap an dong
    if d["tap"]:
        tap = CFG.TAP[d["tap"]]
        ngoai = [x for x in thuong if x not in tap]
        if ngoai:
            loi.append(f"dap an ngoai tap {d['tap']}: {', '.join(ngoai[:4])}")

    # Cung goc tu / khac goc tu
    if d["cung_goc"] is True:
        gocs = {_goc(x) for x in lua}
        if len(gocs) != 1:
            loi.append(f"dang {dang} yeu cau 4 dap an cung goc tu, dang co {sorted(gocs)}")
    elif d["cung_goc"] is False:
        gocs = [_goc(x) for x in lua]
        if len(set(gocs)) == 1:
            loi.append(f"dang {dang} yeu cau dap an khac goc tu")

    gt = _chuan(c.get("giai_thich"))
    if len(gt) < CFG.DO_DAI_GIAI_THICH_MIN:
        loi.append("giai thich qua ngan")
    elif not _co_dau_viet(gt):
        loi.append("giai thich khong co dau tieng Viet")
    c["giai_thich"] = gt
    c["vi_sao_sai"] = _chuan(c.get("vi_sao_sai"))

    if c["part"] == 6:
        doan = _chuan(c.get("doan"))
        thieu = [str(i) for i in (1, 2, 3, 4) if doan.count(f"({i})") != 1]
        if thieu:
            loi.append(f"doan van thieu/lap moc ({', '.join(thieu)})")
        n = len(doan.split())
        if not (CFG.SO_TU_TOI_THIEU_DOAN <= n <= CFG.SO_TU_TOI_DA_DOAN):
            loi.append(f"doan van {n} tu, ngoai khoang")
        c["doan"] = doan

    return loi


def tron_lua_chon(c):
    """Xao vi tri 4 dap an, cap nhat lai chu cai dung.
    Khu thien lech vi tri cua model sinh, va lam pass 2 thanh phep thu doc lap."""
    cap = [(k, c[k]) for k in ("a", "b", "c", "d")]
    dung_txt = c[c["dung"].lower()]
    gia_tri = [v for _, v in cap]
    random.shuffle(gia_tri)
    for k, v in zip(("a", "b", "c", "d"), gia_tri):
        c[k] = v
    c["dung"] = next(k for k in "ABCD" if c[k.lower()] == dung_txt)


# ===========================================================================
# 5. GOOGLE SHEETS
# ===========================================================================
def mo_sheet():
    import gspread
    from google.oauth2.service_account import Credentials
    cre = Credentials.from_service_account_info(
        json.loads(SA_JSON),
        scopes=["https://www.googleapis.com/auth/spreadsheets"])
    return gspread.authorize(cre).open_by_key(SHEET_ID)


def lay_tab(sh, ten, cot):
    try:
        ws = sh.worksheet(ten)
    except Exception:
        log(f"  tao tab moi: {ten}")
        ws = sh.add_worksheet(title=ten, rows=2000, cols=max(len(cot), 10))
        ws.append_row(cot, value_input_option="RAW")
        return ws
    hien = ws.row_values(1)
    if [x.strip() for x in hien[:len(cot)]] != cot:
        if not hien:
            ws.append_row(cot, value_input_option="RAW")
        else:
            log(f"  CANH BAO: header tab {ten} khong khop cau hinh.")
            log(f"    tren Sheet: {hien}")
            log(f"    can co    : {cot}")
    return ws


# ===========================================================================
# 6. SINH
# ===========================================================================
def phan_bo(tong, ty_le):
    """Chia 'tong' cau theo ty le — phuong phap DU LON NHAT.

    Khong duoc don phan du vao muc cuoi danh sach: lam vay thi dang hiem nhat
    (HOA_HOP) lai duoc sinh nhieu nhat khi tong nho.
    """
    s = sum(ty_le.values())
    if not s or tong <= 0:
        return {}
    tho = {k: tong * v / s for k, v in ty_le.items()}
    ra = {k: int(v) for k, v in tho.items()}
    con = tong - sum(ra.values())
    # Phan du chia cho cac muc co phan le lon nhat, uu tien ty le goc cao hon
    thu_tu = sorted(tho, key=lambda k: (-(tho[k] - int(tho[k])), -ty_le[k]))
    for k in thu_tu[:con]:
        ra[k] += 1
    return {k: v for k, v in ra.items() if v > 0}


def sinh_part5(model, so_cau, da_co):
    ra = []
    kh = phan_bo(so_cau, {k: v for k, v in CFG.TY_LE_PART5.items()
                          if not CHI_DANG or k == CHI_DANG})
    if not kh:
        log("  khong dang nao khop CHI_DANG =", CHI_DANG)
        return ra
    log("Phan bo Part 5:", ", ".join(f"{k}={v}" for k, v in kh.items()))

    for dang, n in kh.items():
        con = n
        while con > 0:
            lo = min(LO_P5, con)
            bc = random.choice(CFG.BOI_CANH)
            txt, ly = goi_gemini(model, prompt_p5(dang, lo, bc))
            if txt is None:
                log(f"  {dang}: goi hong -> {ly}")
                if ly == "429":
                    return ra          # de main doi model
                con -= lo
                continue
            if ly == "MAX_TOKENS":
                log(f"  {dang}: CANH BAO tran maxOutputTokens, JSON co the bi cat")
            got = 0
            for o in doc_json_list(txt):
                c = {"part": 5, "dang": dang, "cau": o.get("cau", ""),
                     "a": o.get("a"), "b": o.get("b"), "c": o.get("c"),
                     "d": o.get("d"), "dung": o.get("dung", ""),
                     "giai_thich": o.get("giai_thich"),
                     "vi_sao_sai": o.get("vi_sao_sai"),
                     "do_kho": o.get("do_kho", 2), "model_sinh": model}
                khoa = re.sub(r"[^a-z]", "", _chuan(c["cau"]).lower())[:70]
                if khoa in da_co:
                    continue
                da_co.add(khoa)
                ra.append(c)
                got += 1
            log(f"  {dang}: xin {lo}, nhan {got}")
            con -= lo
    return ra


def sinh_part6(model, so_doan, da_co):
    ra, con = [], so_doan
    while con > 0:
        lo = min(LO_P6, con)
        bc = random.choice(CFG.BOI_CANH)
        txt, ly = goi_gemini(model, prompt_p6(lo, bc), max_tokens=8192)
        if txt is None:
            log(f"  Part6: goi hong -> {ly}")
            if ly == "429":
                return ra
            con -= lo
            continue
        if ly == "MAX_TOKENS":
            log("  Part6: CANH BAO tran maxOutputTokens")
        got = 0
        for o in doc_json_list(txt):
            doan = o.get("doan", "")
            khoa = re.sub(r"[^a-z]", "", _chuan(doan).lower())[:70]
            if not doan or khoa in da_co:
                continue
            da_co.add(khoa)
            nhom = []
            for ct in (o.get("cho_trong") or []):
                nhom.append({
                    "part": 6, "dang": str(ct.get("dang", "")).upper(),
                    "so": ct.get("so"), "doan": doan, "cau": ct.get("cau", ""),
                    "a": ct.get("a"), "b": ct.get("b"), "c": ct.get("c"),
                    "d": ct.get("d"), "dung": ct.get("dung", ""),
                    "giai_thich": ct.get("giai_thich"),
                    "vi_sao_sai": ct.get("vi_sao_sai"),
                    "do_kho": ct.get("do_kho", 2), "model_sinh": model})
            if len(nhom) != 4:
                log(f"  Part6: bo mot doan vi co {len(nhom)} cho trong, phai la 4")
                continue
            ra.append(nhom)
            got += 1
        log(f"  Part6: xin {lo} doan, nhan {got}")
        con -= lo
    return ra


# ===========================================================================
# 7. PASS 2 — MODEL B GIAI MU
# ===========================================================================
def kiem_bang_model(model, cau_list):
    """Gan ket qua vao tung cau: c['kiem'] = dict hoac None."""
    for i in range(0, len(cau_list), LO_KIEM):
        lo = cau_list[i:i + LO_KIEM]
        txt, ly = goi_gemini(model, prompt_kiem(lo), max_tokens=6144, nhiet=0.0)
        if txt is None:
            log(f"  kiem lo {i//LO_KIEM+1}: hong -> {ly}")
            continue
        bang = {}
        for o in doc_json_list(txt):
            if o.get("ma"):
                bang[str(o["ma"])] = o
        hit = 0
        for c in lo:
            kq = bang.get(c["ma"])
            if kq:
                c["kiem"] = kq
                c["model_kiem"] = model
                hit += 1
        log(f"  kiem lo {i//LO_KIEM+1}: {hit}/{len(lo)} cau co ket qua")


def ket_luan(c):
    """Tra ve (trang_thai, ghi_chu)."""
    kq = c.get("kiem")
    if not kq:
        return "XUNG_DOT", "Model kiem khong tra ve ket qua"
    chon = str(kq.get("chon", "")).upper()[:1]
    if kq.get("loi_de"):
        return "XUNG_DOT", "Model kiem bao loi de: " + _chuan(kq.get("ly_do"))
    if kq.get("nhieu_dap_an"):
        return "XUNG_DOT", "Model kiem bao nhieu dap an dung: " + _chuan(kq.get("ly_do"))
    if chon != c["dung"]:
        return "XUNG_DOT", (f"Bat dong: model sinh chon {c['dung']}, "
                            f"model kiem chon {chon}. " + _chuan(kq.get("ly_do")))
    return "DA_DUYET", ""


# ===========================================================================
# 8. MAIN
# ===========================================================================
def main():
    kiem_cau_hinh()
    random.seed()

    log("\n--- Xac thuc model SINH (uu tien han muc) ---")
    m_sinh = chon_model(TEN_SINH, can=1, uu_tien_lite=True)[0]

    log("\n--- Xac thuc model KIEM (uu tien chat luong) ---")
    if EP_MODEL_KIEM:
        m_kiem = EP_MODEL_KIEM
        log(f"  dung model ep buoc: {m_kiem}")
    else:
        m_kiem = chon_model(TEN_KIEM, can=1, uu_tien_lite=False)[0]

    if m_kiem == m_sinh:
        log("*** CANH BAO NANG: model sinh va model kiem TRUNG NHAU.")
        log("    Pass 2 khong con doc lap -> ket qua DA_DUYET khong dang tin.")
        log("    Dung lai, chay 'Do giam khao' de tim model kiem khac.")
    log(f"\nModel sinh = {m_sinh} | Model kiem = {m_kiem}")

    log("\n--- Mo Google Sheet ---")
    sh = mo_sheet()
    ws = lay_tab(sh, "CauHoi", CFG.COT_CAUHOI)
    lay_tab(sh, "KetQuaTOEIC", CFG.COT_KETQUA)

    cu = ws.get_all_values()[1:]
    da_co = set()
    max_p5 = max_p6 = 0
    for r in cu:
        if len(r) > 5 and r[5]:
            da_co.add(re.sub(r"[^a-z]", "", r[5].lower())[:70])
        if len(r) > 4 and r[4]:
            da_co.add(re.sub(r"[^a-z]", "", r[4].lower())[:70])
        ma = r[0] if r else ""
        m = re.match(r"P5-(\d+)", ma)
        if m:
            max_p5 = max(max_p5, int(m.group(1)))
        m = re.match(r"P6-(\d+)", ma)
        if m:
            max_p6 = max(max_p6, int(m.group(1)))
    log(f"Kho hien co {len(cu)} dong | P5 toi {max_p5} | P6 toi {max_p6}")

    log("\n--- Sinh Part 5 ---")
    p5 = sinh_part5(m_sinh, SO_CAU_P5, da_co) if SO_CAU_P5 else []
    log("\n--- Sinh Part 6 ---")
    p6 = sinh_part6(m_sinh, SO_DOAN_P6, da_co) if SO_DOAN_P6 else []

    # Gan ma + kiem co hoc
    log("\n--- Lop kiem co hoc ---")
    tat_ca, bo = [], []
    i5 = max_p5
    for c in p5:
        i5 += 1
        c["ma"] = f"P5-{i5:04d}"
        c["ma_doan"] = ""
        c["thu_tu"] = ""
        loi = kiem_co_hoc(c)
        if loi:
            bo.append((c["ma"], c["dang"], loi))
        else:
            tron_lua_chon(c)
            tat_ca.append(c)
    i6 = max_p6
    for nhom in p6:
        i6 += 1
        md = f"P6-{i6:04d}"
        loi_doan, tam = [], []
        for j, c in enumerate(nhom, 1):
            c["ma"] = f"{md}-{j}"
            c["ma_doan"] = md
            c["thu_tu"] = j
            loi = kiem_co_hoc(c)
            if loi:
                loi_doan.append((c["ma"], c["dang"], loi))
            else:
                tam.append(c)
        if loi_doan:
            # Doan khong tron ven -> bo ca doan, vi 4 cho trong dinh nhau
            bo.extend(loi_doan)
            log(f"  bo ca doan {md} vi co cho trong hong")
            i6 -= 1
            continue
        for c in tam:
            tron_lua_chon(c)
        tat_ca.extend(tam)

    log(f"Qua lop co hoc: {len(tat_ca)} | Bi loai: {len(bo)}")
    for ma, dang, loi in bo[:15]:
        log(f"  LOAI {ma} [{dang}]: {'; '.join(loi)}")
    if len(bo) > 15:
        log(f"  ... va {len(bo)-15} cau nua")

    if not tat_ca:
        log("\nKhong con cau nao de ghi. DUNG.")
        return

    log("\n--- Pass 2: model B giai mu ---")
    kiem_bang_model(m_kiem, tat_ca)

    log("\n--- Ket luan ---")
    dong, dem = [], {"DA_DUYET": 0, "XUNG_DOT": 0}
    luc = now_vn().strftime("%Y-%m-%d %H:%M")
    for c in tat_ca:
        tt, gc = ket_luan(c)
        dem[tt] += 1
        dong.append([
            c["ma"], c["part"], c["ma_doan"], c["thu_tu"],
            c.get("doan", ""), c["cau"],
            c["a"], c["b"], c["c"], c["d"], c["dung"], c["dang"],
            c["giai_thich"], c["vi_sao_sai"], c.get("do_kho", 2),
            tt, luc, c.get("model_sinh", ""), c.get("model_kiem", ""),
            0, 0, 0, gc,
        ])

    ws.append_rows(dong, value_input_option="RAW")

    tong = len(dong)
    log(f"\nDa ghi {tong} dong vao tab CauHoi.")
    log(f"  DA_DUYET  : {dem['DA_DUYET']} ({dem['DA_DUYET']*100//tong}%)")
    log(f"  XUNG_DOT  : {dem['XUNG_DOT']} ({dem['XUNG_DOT']*100//tong}%)  <- can duyet tay")

    # Thong ke theo dang de thay dang nao model sinh kem
    theo_dang = {}
    for c, d in zip(tat_ca, dong):
        k = c["dang"]
        theo_dang.setdefault(k, [0, 0])
        theo_dang[k][0] += 1
        if d[15] == "XUNG_DOT":
            theo_dang[k][1] += 1
    log("\nTy le xung dot theo dang (cao = dang do model sinh kem tin cay):")
    for k, (n, x) in sorted(theo_dang.items(), key=lambda i: -i[1][1] / max(i[1][0], 1)):
        log(f"  {k:16s} {x}/{n}")

    # Xuat rieng cac cau XUNG_DOT ra CSV de tai ve va nho nguoi khac phan xu
    xd = [d for d in dong if d[15] == "XUNG_DOT"]
    if xd:
        import csv
        ten = f"xungdot_{now_vn():%Y%m%d_%H%M}.csv"
        with open(ten, "w", newline="", encoding="utf-8-sig") as f:
            w = csv.writer(f)
            w.writerow(CFG.COT_CAUHOI)
            w.writerows(xd)
        log(f"\nDa xuat {len(xd)} cau XUNG_DOT ra file: {ten}")
        log("Tai file nay o muc Artifacts cuoi trang run.")

    log("\nBuoc tiep theo: tai CSV xung dot o Artifacts, gui di phan xu.")
    log("Cac cau DA_DUYET da dung duoc ngay, khong can cho.")


if __name__ == "__main__":
    main()
