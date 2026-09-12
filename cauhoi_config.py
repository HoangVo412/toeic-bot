# -*- coding: utf-8 -*-
"""
Cau hinh ngan hang cau hoi TOEIC Part 5-6 (NGU PHAP THUAN).

Tach cau hinh khoi logic — dung nguyen tac muc 5.4 PROJECT-KNOWLEDGE.md.
Moi thu can chinh (them dang, sua tap dap an, doi ty le) nam o day.
"""

# ---------------------------------------------------------------------------
# 1. DANH MUC DANG NGU PHAP
# ---------------------------------------------------------------------------
# Moi dang co:
#   ten     : nhan tieng Viet, dung de hien thi trong /status
#   goi_y   : mo ta dua vao prompt cho Gemini
#   tap     : ten tap dap an dong de tu kiem co hoc (None = khong kiem duoc)
#   cung_goc: True  -> 4 dap an PHAI cung goc tu (vd: apply/application/applied)
#             False -> 4 dap an PHAI KHAC goc tu
#             None  -> khong kiem
#   part    : 5, 6 hoac "ca"

DANG = {
    "TU_LOAI": {
        "ten": "Từ loại (word form)",
        "goi_y": ("Bon dap an la bon dang tu cung mot goc: danh tu, dong tu, "
                  "tinh tu, trang tu. Cho trong o vi tri ma chuc nang ngu phap "
                  "quyet dinh duy nhat mot dang."),
        "tap": None, "cung_goc": True, "part": "ca",
    },
    "THI": {
        "ten": "Thì của động từ",
        "goi_y": ("Bon dap an la bon dang thi cua CUNG mot dong tu. Cau phai "
                  "co moc thoi gian ro rang (trang ngu thoi gian, menh de phu) "
                  "de chi dung mot thi la dung."),
        "tap": None, "cung_goc": True, "part": "ca",
    },
    "THE": {
        "ten": "Thể chủ động / bị động",
        "goi_y": ("Bon dap an gom dang chu dong va bi dong cua cung dong tu. "
                  "Quan he giua chu ngu va dong tu phai quyet dinh ro the."),
        "tap": None, "cung_goc": True, "part": "ca",
    },
    "HOA_HOP": {
        "ten": "Hòa hợp chủ ngữ – động từ",
        "goi_y": ("Chu ngu co thanh phan xen giua (menh de quan he, cum gioi tu) "
                  "lam nguoi hoc de nham so it/so nhieu."),
        "tap": None, "cung_goc": True, "part": 5,
    },
    "GIOI_TU": {
        "ten": "Giới từ",
        "goi_y": ("Bon dap an la bon gioi tu khac nhau. Ngu canh phai quyet dinh "
                  "duy nhat mot gioi tu dung (cum co dinh, chi thoi gian, noi chon)."),
        "tap": "GIOI_TU", "cung_goc": False, "part": "ca",
    },
    "LIEN_TU": {
        "ten": "Liên từ đẳng lập",
        "goi_y": ("Bon dap an la lien tu dang lap hoac cap lien tu tuong quan. "
                  "Quan he logic giua hai ve phai ro rang."),
        "tap": "LIEN_TU", "cung_goc": False, "part": "ca",
    },
    "MENH_DE": {
        "ten": "Liên từ phụ thuộc vs giới từ",
        "goi_y": ("Phan biet tu dung truoc MENH DE (although, because, while) voi "
                  "tu dung truoc CUM DANH TU (despite, because of, during). Cho "
                  "trong dat truoc mot trong hai cau truc do."),
        "tap": "MENH_DE_HON_HOP", "cung_goc": False, "part": "ca",
    },
    "QUAN_HE": {
        "ten": "Mệnh đề quan hệ",
        "goi_y": ("Bon dap an la dai tu quan he hoac trang tu quan he. Tien ngu "
                  "va chuc nang trong menh de phai quyet dinh duy nhat mot lua chon."),
        "tap": "QUAN_HE", "cung_goc": False, "part": 5,
    },
    "DAI_TU": {
        "ten": "Đại từ",
        "goi_y": ("Bon dap an la bon dang cua cung mot dai tu: chu ngu, tan ngu, "
                  "so huu, phan than."),
        "tap": "DAI_TU", "cung_goc": None, "part": "ca",
    },
    "DONG_TU_NGUYEN": {
        "ten": "To V / V-ing / nguyên mẫu",
        "goi_y": ("Dong tu chinh hoac gioi tu dung truoc quyet dinh dang cua dong "
                  "tu theo sau (to V, V-ing, V nguyen mau khong to)."),
        "tap": None, "cung_goc": True, "part": 5,
    },
    "PHAN_TU": {
        "ten": "Phân từ làm bổ ngữ",
        "goi_y": ("Phan biet phan tu hien tai (V-ing, chu dong) voi phan tu qua "
                  "khu (V-ed, bi dong) khi rut gon menh de hoac lam tinh tu."),
        "tap": None, "cung_goc": True, "part": 5,
    },
    "SO_SANH": {
        "ten": "So sánh",
        "goi_y": ("Bon dap an gom dang nguyen, so sanh hon, so sanh nhat cua cung "
                  "tinh tu/trang tu. Cau truc so sanh (than, the, as...as) phai ro."),
        "tap": None, "cung_goc": True, "part": 5,
    },
    "LUONG_TU": {
        "ten": "Lượng từ và từ hạn định",
        "goi_y": ("Bon dap an la luong tu khac nhau. Danh tu theo sau (dem duoc / "
                  "khong dem duoc, so it / so nhieu) quyet dinh dap an."),
        "tap": "LUONG_TU", "cung_goc": False, "part": 5,
    },
    "TU_NOI": {
        "ten": "Từ nối liên kết đoạn",
        "goi_y": ("CHI DUNG CHO PART 6. Bon dap an la trang tu lien ket. Quan he "
                  "logic voi cau LIEN TRUOC trong doan phai quyet dinh dap an — "
                  "doc rieng cau chua cho trong thi KHONG the chon dung."),
        "tap": "TU_NOI", "cung_goc": False, "part": 6,
    },
}

# Ty le sinh cho Part 5 (tong khong can bang 100, script tu chuan hoa)
TY_LE_PART5 = {
    "TU_LOAI": 22, "THI": 16, "GIOI_TU": 12, "MENH_DE": 10,
    "THE": 8, "DONG_TU_NGUYEN": 7, "DAI_TU": 6, "QUAN_HE": 6,
    "LIEN_TU": 5, "LUONG_TU": 4, "PHAN_TU": 2, "SO_SANH": 1, "HOA_HOP": 1,
}

# Ty le cho 4 cho trong cua mot doan Part 6
TY_LE_PART6 = {"TU_NOI": 1, "THI": 1, "TU_LOAI": 1, "GIOI_TU": 1}

# ---------------------------------------------------------------------------
# 2. TAP DAP AN DONG — dung de tu kiem co hoc
# ---------------------------------------------------------------------------
# Neu dang co khai "tap", moi dap an PHAI nam trong tap nay (so khong phan biet
# hoa thuong). Lop chan nay bat duoc truong hop model sinh sai dang.

TAP = {}

TAP["GIOI_TU"] = {
    "of", "in", "on", "at", "by", "for", "from", "to", "with", "within", "without",
    "during", "since", "until", "till", "through", "throughout", "among",
    "amongst", "between", "beyond", "under", "over", "above", "below",
    "against", "toward", "towards", "upon", "into", "onto", "off", "about",
    "across", "along", "around", "before", "after", "behind", "beside",
    "besides", "despite", "except", "near", "per", "regarding", "concerning",
    "via", "following", "including", "excluding", "unlike", "like", "as",
    "prior to", "due to", "according to", "because of", "in addition to",
    "instead of", "along with", "as of", "ahead of", "next to", "out of",
    "thanks to", "owing to", "in spite of", "apart from", "aside from",
    "rather than", "subject to", "up to", "close to", "in front of",
    "on behalf of", "in accordance with", "with regard to", "regardless of",
    "by means of", "in terms of", "as for", "except for", "other than",
    "amid", "beneath", "underneath", "opposite", "outside", "inside",
    "past", "plus", "minus", "notwithstanding", "pending", "versus",
    "in light of", "in response to", "with respect to", "in favor of",
    "contrary to", "relative to", "pursuant to", "by way of",
}

TAP["LIEN_TU"] = {
    "and", "but", "or", "nor", "so", "yet", "for",
    "both", "either", "neither", "not only", "but also", "whether",
    "as well as", "rather than",
}

TAP["MENH_DE"] = {
    "because", "although", "though", "even though", "even if", "while",
    "whereas", "if", "unless", "when", "whenever", "before", "after",
    "since", "until", "as", "as soon as", "as long as", "provided that",
    "providing that", "in case", "so that", "in order that", "once",
    "given that", "now that", "except that", "whether", "wherever",
    "assuming that", "on condition that",
}

# Dang MENH_DE co dap an nhieu lan la gioi tu -> tap hop nhat
TAP["MENH_DE_HON_HOP"] = TAP["MENH_DE"] | TAP["GIOI_TU"]

TAP["QUAN_HE"] = {
    "who", "whom", "whose", "which", "that", "where", "when", "why",
    "what", "whoever", "whomever", "whichever", "whatever",
}

TAP["DAI_TU"] = {
    "i", "me", "my", "mine", "myself",
    "you", "your", "yours", "yourself", "yourselves",
    "he", "him", "his", "himself",
    "she", "her", "hers", "herself",
    "it", "its", "itself",
    "we", "us", "our", "ours", "ourselves",
    "they", "them", "their", "theirs", "themselves",
    "one", "oneself", "one's",
}

TAP["LUONG_TU"] = {
    "much", "many", "more", "most", "few", "a few", "fewer", "fewest",
    "little", "a little", "less", "least", "several", "each", "every",
    "all", "both", "either", "neither", "any", "some", "none", "no",
    "another", "other", "others", "the other", "the others", "enough",
    "plenty of", "a lot of", "lots of", "a number of", "the number of",
    "a great deal of", "a variety of", "every other",
}

TAP["TU_NOI"] = {
    "however", "therefore", "thus", "hence", "moreover", "furthermore",
    "nevertheless", "nonetheless", "in addition", "additionally",
    "in contrast", "on the contrary", "on the other hand", "for example",
    "for instance", "as a result", "consequently", "accordingly",
    "meanwhile", "in the meantime", "otherwise", "similarly", "likewise",
    "in fact", "indeed", "instead", "finally", "subsequently", "afterward",
    "afterwards", "that is", "namely", "in other words", "in short",
    "overall", "in summary", "to that end", "at the same time", "even so",
    "of course", "in particular", "specifically", "regardless", "besides",
    "first", "second", "then", "next", "also", "still", "rather",
}

# ---------------------------------------------------------------------------
# 3. NGUONG TU KIEM CO HOC
# ---------------------------------------------------------------------------
SO_TU_TOI_THIEU_P5 = 8     # cau Part 5 ngan hon -> nghi ngo
SO_TU_TOI_DA_P5 = 32       # dai hon -> nghi ngo
SO_TU_TOI_THIEU_DOAN = 55  # doan Part 6
SO_TU_TOI_DA_DOAN = 180
DO_DAI_GIAI_THICH_MIN = 15 # so ky tu toi thieu cua GiaiThichVN

# Boi canh de yeu cau Gemini sinh cau — giu dung khong khi de TOEIC that
BOI_CANH = [
    "email noi bo thong bao lich hop hoac thay doi quy trinh",
    "thong bao bao tri toa nha, thang may, he thong may tinh",
    "hop dong, don dat hang, hoa don, dieu khoan thanh toan",
    "tuyen dung, phong van, dao tao nhan vien moi",
    "bao cao doanh thu quy, ngan sach, chi phi van hanh",
    "dich vu khach hang, bao hanh, doi tra san pham",
    "du lich cong tac, dat phong khach san, ve may bay",
    "quang cao san pham moi, chuong trinh khuyen mai",
    "thong cao bao chi ve mo rong chi nhanh, sap nhap",
    "lich giao hang, kho van, chuoi cung ung",
]

# Cac cot cua tab CauHoi — THU TU NAY PHAI KHOP voi header tren Sheet
COT_CAUHOI = [
    "MaCau", "Part", "MaDoan", "ThuTuTrong", "DoanVan", "CauHoi",
    "DapAnA", "DapAnB", "DapAnC", "DapAnD", "Dung", "Dang",
    "GiaiThichVN", "ViSaoSai", "DoKho", "TrangThai", "NgayTao",
    "ModelSinh", "ModelKiem", "LanGui", "LanDung", "LanSai", "GhiChu",
]

COT_KETQUA = [
    "Luc", "MaCau", "Dang", "Part", "ChonDapAn", "Dung", "GiayLam", "PhienID",
]
