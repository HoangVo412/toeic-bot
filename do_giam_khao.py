# -*- coding: utf-8 -*-
"""
do_giam_khao.py — Do nang luc cac model truoc khi giao vai GIAM KHAO.

Van de: pass 2 trong gen_cauhoi.py quyet dinh cau nao duoc DA_DUYET tu dong.
Neu model do yeu thi ca kho cau hoi khong dang tin, va khong ai biet.

Cach do: lay bo CLOTH (99.433 cau dien khuyet do GIAO VIEN soan, co dap an
chuan, giay phep MIT) — nhung LOC lai chi giu phan NGU PHAP, vi phan lon CLOTH
la tu vung trong van ke chuyen va cau bi tach khoi doan nen nhieu cau khong co
dap an duy nhat.

Bo loc dung LAI chinh bo may cua cauhoi_config.py:
  · 4 phuong an nam tron trong mot tap dong (gioi tu / lien tu / dai tu / luong tu)
  · hoac 4 phuong an cung goc tu (tu loai / thi / the)
Do dung la ho so Part 5, va loai han nhom cau phu thuoc ngu canh.

QUAN TRONG: dung chinh ham prompt_kiem() cua gen_cauhoi.py, khong viet prompt
rieng. Neu viet prompt khac thi phep do khong do dung thu dang chay that —
dung bai hoc muc 2.5 va 3.4 cua PROJECT-KNOWLEDGE.md.

Ket qua doc theo XEP HANG giua cac model, KHONG doc theo con so tuyet doi:
CLOTH van con cau nhieu, nen 85% o day khong co nghia la 85% tren de TOEIC.

Bien moi truong: GEMINI_KEY
Bien tuy chon: SO_CAU (mac dinh 48), MODEL_THEM (them ten model, cach nhau dau phay)
"""

import json
import os
import random
import re
import sys
import urllib.request

import gen_cauhoi as G
import cauhoi_config as CFG

log = G.log

SO_CAU = int(os.environ.get("SO_CAU") or 48)
MODEL_THEM = [x.strip() for x in (os.environ.get("MODEL_THEM") or "").split(",") if x.strip()]

# [??] CHUA KIEM CHUNG duong dan resolve. Da xac nhan kho va ten file ton tai:
# https://huggingface.co/datasets/AndyChiang/cloth  (giay phep MIT)
# Neu URL nay hong, xem log de biet ma loi va doi sang URL con lai.
NGUON = [
    "https://huggingface.co/datasets/AndyChiang/cloth/resolve/main/CLOTH_test_cleaned.json",
    "https://huggingface.co/datasets/AndyChiang/cloth/resolve/main/CLOTH_valid_cleaned.json",
]


# ---------------------------------------------------------------------------
# 1. TAI BO DU LIEU
# ---------------------------------------------------------------------------
def tai_cloth():
    for url in NGUON:
        log(f"Tai: {url}")
        try:
            req = urllib.request.Request(url, headers={"User-Agent": "toeic-bot/1.0"})
            with urllib.request.urlopen(req, timeout=180) as r:
                raw = r.read()
            log(f"  OK, {len(raw)/1024/1024:.2f} MB")
            d = json.loads(raw)
            if isinstance(d, dict):
                for k in ("data", "rows", "train", "test"):
                    if isinstance(d.get(k), list):
                        d = d[k]
                        break
            if isinstance(d, list) and d:
                log(f"  {len(d)} dong | truong: {sorted(d[0].keys())}")
                return d
            log("  CAU TRUC LA, bo qua nguon nay")
        except Exception as e:
            log(f"  HONG: {type(e).__name__}: {e}")
    log("\nLOI: khong tai duoc bo du lieu doi chung.")
    log("Kiem tra: runner co ra Internet khong, huggingface.co co doi duong dan khong.")
    sys.exit(1)


# ---------------------------------------------------------------------------
# 2. LOC VE DUNG HO SO NGU PHAP PART 5
# ---------------------------------------------------------------------------
TAP_XET = {
    "GIOI_TU": CFG.TAP["GIOI_TU"],
    "LIEN_TU": CFG.TAP["LIEN_TU"] | CFG.TAP["MENH_DE"],
    "DAI_TU": CFG.TAP["DAI_TU"],
    "LUONG_TU": CFG.TAP["LUONG_TU"],
    "QUAN_HE": CFG.TAP["QUAN_HE"],
}


def phan_loai(lua):
    """Tra ve ma dang neu 4 phuong an dat ho so ngu phap, nguoc lai None."""
    thuong = [x.strip().lower() for x in lua]
    if len(set(thuong)) != 4:
        return None
    for ten, tap in TAP_XET.items():
        if all(x in tap for x in thuong):
            return ten
    gocs = {G._goc(x) for x in lua}
    if len(gocs) == 1 and "" not in gocs:
        return "CUNG_GOC"      # tu loai / thi / the
    return None


def loc(rows, can):
    ra, thay = [], set()
    dem_dang = {}
    random.shuffle(rows)
    for r in rows:
        cau = (r.get("sentence") or "").strip()
        dap = (r.get("answer") or "").strip()
        nhieu = r.get("distractors") or []
        if not cau or not dap or len(nhieu) != 3:
            continue
        if "[MASK]" not in cau:
            continue
        # Cau qua ngan / qua dai thi bo, giong nguong cua Part 5
        n = len(cau.replace("[MASK]", " ").split())
        if not (CFG.SO_TU_TOI_THIEU_P5 <= n <= CFG.SO_TU_TOI_DA_P5):
            continue
        # CLOTH co cau con dinh so thu tu cua cho trong khac (vd "41", "52")
        if re.search(r"(?<!\w)\d{2}(?!\w)", cau):
            continue
        lua = [dap] + list(nhieu)
        dang = phan_loai(lua)
        if not dang:
            continue
        khoa = re.sub(r"[^a-z]", "", cau.lower())[:60]
        if khoa in thay:
            continue
        thay.add(khoa)
        random.shuffle(lua)
        vt = lua.index(dap)
        ra.append({
            "ma": f"CL-{len(ra)+1:04d}", "dang": dang,
            "cau": cau.replace("[MASK]", "____"),
            "a": lua[0], "b": lua[1], "c": lua[2], "d": lua[3],
            "dung": "ABCD"[vt],
        })
        dem_dang[dang] = dem_dang.get(dang, 0) + 1
        if len(ra) >= can:
            break
    return ra, dem_dang


# ---------------------------------------------------------------------------
# 3. CHAM MOT MODEL
# ---------------------------------------------------------------------------
def cham(model, bo):
    dung = sai = khong_tra = 0
    co_nhieu = co_loi = 0
    sai_theo_dang = {}
    for i in range(0, len(bo), G.LO_KIEM):
        lo = bo[i:i + G.LO_KIEM]
        txt, ly = G.goi_gemini(model, G.prompt_kiem(lo), max_tokens=6144, nhiet=0.0)
        if txt is None:
            log(f"    lo {i//G.LO_KIEM+1}: HONG -> {ly}")
            khong_tra += len(lo)
            if ly == "429":
                log("    het han muc -> dung cham model nay")
                break
            continue
        bang = {str(o.get("ma")): o for o in G.doc_json_list(txt) if o.get("ma")}
        for c in lo:
            kq = bang.get(c["ma"])
            if not kq:
                khong_tra += 1
                continue
            if kq.get("nhieu_dap_an"):
                co_nhieu += 1
            if kq.get("loi_de"):
                co_loi += 1
            if str(kq.get("chon", "")).upper()[:1] == c["dung"]:
                dung += 1
            else:
                sai += 1
                sai_theo_dang[c["dang"]] = sai_theo_dang.get(c["dang"], 0) + 1
        log(f"    lo {i//G.LO_KIEM+1}: dung {dung}, sai {sai}, khong tra {khong_tra}")
    tra_loi = dung + sai
    return {
        "model": model, "dung": dung, "sai": sai, "khong_tra": khong_tra,
        "ty_le": (dung / tra_loi * 100) if tra_loi else 0.0,
        "bao_nhieu_dap_an": (co_nhieu / tra_loi * 100) if tra_loi else 0.0,
        "bao_loi_de": (co_loi / tra_loi * 100) if tra_loi else 0.0,
        "sai_theo_dang": sai_theo_dang,
    }


# ---------------------------------------------------------------------------
# 4. MAIN
# ---------------------------------------------------------------------------
def main():
    if not G.GEMINI_KEY:
        log("LOI: thieu GEMINI_KEY")
        sys.exit(1)
    random.seed(20260912)     # co dinh de hai lan chay so sanh duoc voi nhau

    log("=== 1. Tai bo doi chung CLOTH ===")
    rows = tai_cloth()

    log("\n=== 2. Loc ve ho so ngu phap Part 5 ===")
    bo, dem = loc(rows, SO_CAU)
    log(f"Giu lai {len(bo)}/{SO_CAU} cau can do")
    for k, v in sorted(dem.items(), key=lambda x: -x[1]):
        log(f"  {k:10s} {v}")
    if len(bo) < 12:
        log("LOI: khong du cau sau khi loc. Noi long nguong trong loc().")
        sys.exit(1)
    log("\n3 cau mau:")
    for c in bo[:3]:
        log(f"  [{c['dang']}] {c['cau']}")
        log(f"      A.{c['a']}  B.{c['b']}  C.{c['c']}  D.{c['d']}  -> {c['dung']}")

    log("\n=== 3. Xac thuc cac model ung vien ===")
    ung_vien = []
    for m in (MODEL_THEM + G.TEN_KIEM):
        if m in ung_vien:
            continue
        txt, ly = G.goi_gemini(m, 'Tra ve dung JSON: {"ok":1}', max_tokens=64, nhiet=0)
        if txt:
            ung_vien.append(m)
            log(f"  OK   : {m}")
        else:
            log(f"  hong : {m} -> {ly}")
        if len(ung_vien) >= 3:
            break
    # Mot model Lite lam DOI CHUNG — de thay chenh lech co that hay khong
    lite = G.chon_model(G.TEN_SINH, can=1, uu_tien_lite=True)[0]
    if lite not in ung_vien:
        ung_vien.append(lite)
    log(f"Se cham: {', '.join(ung_vien)}")

    log("\n=== 4. Cham ===")
    kq = []
    for m in ung_vien:
        log(f"  -- {m} --")
        kq.append(cham(m, bo))

    log("\n=== 5. KET QUA (doc theo XEP HANG, khong theo con so tuyet doi) ===")
    kq.sort(key=lambda x: -x["ty_le"])
    log(f"{'MODEL':34s} {'DUNG%':>7s} {'D/S':>9s} {'BAO NHIEU DA%':>14s} {'BAO LOI DE%':>12s}")
    for r in kq:
        log(f"{r['model']:34s} {r['ty_le']:6.1f}% {r['dung']:4d}/{r['sai']:<4d}"
            f" {r['bao_nhieu_dap_an']:13.1f}% {r['bao_loi_de']:11.1f}%")

    tot = kq[0]
    log(f"\nDang sai nhieu nhat cua {tot['model']}:")
    for k, v in sorted(tot["sai_theo_dang"].items(), key=lambda x: -x[1]) or [("(khong sai)", 0)]:
        log(f"  {k:10s} {v}")

    log("\n--- Doc ket qua ---")
    log("· Cot DUNG% cao  = giai gioi, dang tin khi phan xu bat dong")
    log("· Cot BAO NHIEU DA% cao bat thuong = model khat khe thua, se day")
    log("  nhieu cau tot vao XUNG_DOT -> ton cong phan xu ma khong loi ich")
    log("· Neu model manh KHONG hon model Lite dang ke thi doi model kiem la")
    log("  vo nghia, phai tim cach khac (nha cung cap khac, hoac duyet tay)")
    log(f"\nDat vao workflow 'Sinh cau hoi', o model_kiem: {tot['model']}")


if __name__ == "__main__":
    main()
