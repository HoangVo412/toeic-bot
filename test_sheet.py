# -*- coding: utf-8 -*-
"""
Test ket noi Google Sheets.
Chi lam 2 viec: DOC mot o co san, va GHI mot dong vao tab NhatKyOn.
Chay duoc = toan bo chuoi Google Cloud -> Service Account -> Sheets da thong.
"""
import os
import sys
import json
from datetime import datetime, timezone, timedelta

VN = timezone(timedelta(hours=7))
TEN_TAB_TU_VUNG = "TuVung"
TEN_TAB_NHAT_KY = "NhatKyOn"


def die(ly_do, huong_xu_ly=""):
    print("")
    print("=" * 60)
    print("THAT BAI: " + ly_do)
    if huong_xu_ly:
        print("HUONG XU LY: " + huong_xu_ly)
    print("=" * 60)
    sys.exit(1)


def main():
    # ---------- 1. In cau hinh dang dung ----------
    sa_raw = os.environ.get("GOOGLE_SA_JSON", "")
    sheet_id = os.environ.get("SHEET_ID", "")

    print("=" * 60)
    print("CAU HINH DANG DUNG")
    print("=" * 60)
    print("SHEET_ID       : " + (sheet_id if sheet_id else "(TRONG)"))
    print("GOOGLE_SA_JSON : " + (
        "co, %d ky tu" % len(sa_raw) if sa_raw else "(TRONG)"))

    if not sheet_id:
        die("Bien SHEET_ID chua toi duoc script.",
            "Vao repo > Settings > Secrets and variables > Actions > tab Variables, "
            "tao bien ten SHEET_ID.")
    if not sa_raw:
        die("Bien GOOGLE_SA_JSON chua toi duoc script.",
            "Vao repo > Settings > Secrets and variables > Actions > tab Secrets, "
            "tao secret ten GOOGLE_SA_JSON.")

    # ---------- 2. Doc file JSON ----------
    try:
        sa = json.loads(sa_raw)
    except Exception as e:
        die("Noi dung GOOGLE_SA_JSON khong phai JSON hop le (%s)." % e,
            "Mo lai file .json tai ve tu Google Cloud, Ctrl+A, Ctrl+C, "
            "roi dan LAI TOAN BO vao Secret. Khong sua gi ben trong.")

    for khoa in ("client_email", "private_key", "project_id"):
        if khoa not in sa:
            die("File JSON thieu truong '%s'." % khoa,
                "Co the da dan nham file. Phai la file key cua Service Account.")

    print("project_id     : " + sa["project_id"])
    print("client_email   : " + sa["client_email"])
    print("")
    print(">> Email tren PHAI nam trong danh sach Share cua file Sheet, quyen Editor.")
    print("")

    # ---------- 3. Ket noi ----------
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError as e:
        die("Thieu thu vien: %s" % e, "Kiem tra buoc 'Cai thu vien' trong workflow.")

    scopes = [
        "https://www.googleapis.com/auth/spreadsheets",
        "https://www.googleapis.com/auth/drive",
    ]
    try:
        creds = Credentials.from_service_account_info(sa, scopes=scopes)
        gc = gspread.authorize(creds)
    except Exception as e:
        die("Khong tao duoc thong tin dang nhap: %s" % e,
            "Thuong do noi dung JSON bi sua hoac thieu ky tu xuong dong "
            "trong truong private_key.")

    print("[1/4] Tao thong tin dang nhap: OK")

    # ---------- 4. Mo file ----------
    try:
        sh = gc.open_by_key(sheet_id)
    except Exception as e:
        loi = str(e)
        if "PERMISSION_DENIED" in loi or "403" in loi:
            die("Bi tu choi quyen truy cap (403).",
                "1) Da Share file Sheet cho email " + sa["client_email"] +
                " voi quyen Editor chua? 2) Da bat CA HAI: Google Sheets API "
                "va Google Drive API trong project '" + sa["project_id"] + "' chua?")
        if "not found" in loi.lower() or "404" in loi:
            die("Khong tim thay file Sheet voi ID nay.",
                "Kiem tra lai SHEET_ID. Day la chuoi nam giua /d/ va /edit "
                "trong duong dan file Sheet.")
        die("Loi khi mo file Sheet: %s" % loi)

    print("[2/4] Mo file Sheet: OK  -> ten file: '%s'" % sh.title)

    ten_cac_tab = [ws.title for ws in sh.worksheets()]
    print("      Cac tab dang co: " + ", ".join(ten_cac_tab))

    # ---------- 5. DOC thu ----------
    try:
        ws = sh.worksheet(TEN_TAB_TU_VUNG)
    except Exception:
        die("Khong tim thay tab '%s'." % TEN_TAB_TU_VUNG,
            "Ten tab phan biet chu hoa chu thuong. Cac tab dang co: " +
            ", ".join(ten_cac_tab))

    tieu_de = ws.row_values(1)
    dong_2 = ws.row_values(2)
    so_dong = len(ws.col_values(1))

    print("[3/4] Doc tab '%s': OK" % TEN_TAB_TU_VUNG)
    print("      So dong (ke ca tieu de): %d" % so_dong)
    print("      Tieu de : " + " | ".join(tieu_de[:6]))
    print("      Dong 2  : " + " | ".join(dong_2[:6]))

    if so_dong != 1001:
        print("      CANH BAO: mong doi 1001 dong (1 tieu de + 1000 tu), "
              "dang co %d. Kiem tra lai buoc Import." % so_dong)

    # ---------- 6. GHI thu ----------
    try:
        ws_log = sh.worksheet(TEN_TAB_NHAT_KY)
    except Exception:
        die("Khong tim thay tab '%s'." % TEN_TAB_NHAT_KY,
            "Cac tab dang co: " + ", ".join(ten_cac_tab))

    bay_gio = datetime.now(VN).strftime("%Y-%m-%d %H:%M:%S")
    try:
        ws_log.append_row(
            [bay_gio, 0, "__TEST_KET_NOI__", "-", "-", "-", "-"],
            value_input_option="USER_ENTERED",
        )
    except Exception as e:
        loi = str(e)
        if "403" in loi or "PERMISSION_DENIED" in loi:
            die("Doc duoc nhung KHONG ghi duoc (403).",
                "File Sheet dang share cho service account voi quyen Viewer. "
                "Doi sang Editor.")
        die("Loi khi ghi vao tab '%s': %s" % (TEN_TAB_NHAT_KY, loi))

    print("[4/4] Ghi vao tab '%s': OK" % TEN_TAB_NHAT_KY)
    print("")
    print("=" * 60)
    print("THANH CONG. Chuoi Google Cloud -> Sheets da thong.")
    print("Mo tab '%s' se thay mot dong moi ghi '__TEST_KET_NOI__'." % TEN_TAB_NHAT_KY)
    print("Xoa dong do di sau khi kiem tra xong.")
    print("=" * 60)


if __name__ == "__main__":
    main()
