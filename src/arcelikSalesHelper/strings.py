"""Turkish user-visible text: the single catalog / translation boundary.

Rules
-----
* Every string a person can read (labels, buttons, errors, warnings, tooltips,
  formula explanations, dialog texts, history headings) lives here.
* Plain constants for fixed text, small functions for text with values. Values
  are passed in already formatted, so this module imports nothing from the
  application and stays safe to use from ``domain/`` (no Qt, no sqlite3).
* Internal identifiers, database columns, CSV field names and log messages stay
  English and do not belong here.
* A later language selector replaces this module with a lookup that keeps the
  same names; callers never contain literal user-facing text.
"""

from __future__ import annotations

# ======================================================================
# Shared words
# ======================================================================

NOT_AVAILABLE = "Yok"
EMPTY_VALUE = "(boş)"
NONE_DASH = "—"
ARCHIVED_SUFFIX = " (arşivlendi)"

# Standard dialog buttons (Qt only translates these when its own .qm files are
# loaded, so the UI sets them explicitly as well).
BTN_OK = "Tamam"
BTN_CANCEL = "İptal"
BTN_SAVE = "Kaydet"
BTN_YES = "Evet"
BTN_NO = "Hayır"
BTN_CLOSE = "Kapat"

# ======================================================================
# Money parsing (domain/money.py)
# ======================================================================

MONEY_EMPTY = "Bir tutar girin."
MONEY_NEGATIVE = "Negatif tutarlara izin verilmez."
MONEY_CHARS = "Yalnızca rakam ile '.' veya ',' ayırıcılarını kullanın (örneğin 54.999,00)."
MONEY_FORMAT = "Geçersiz sayı biçimi."
MONEY_GROUPING = "Geçersiz binlik gruplama (örneğin 1.234.567,89)."
MONEY_COMMAS = "Yalnızca bir ondalık virgülü kullanılabilir."
MONEY_TOO_LONG = "Tutar çok uzun."


def money_ambiguous_hint(read_as: str) -> str:
    return f"{read_as} olarak okundu. Ondalık için virgül kullanın (örneğin 1,234)."


# ======================================================================
# Validation (domain/validation.py, products.py, stock.py, pricing.py)
# ======================================================================

VAL_QUANTITY = "Adet, en az 1 olan bir tam sayı olmalıdır."
VAL_REGULAR_PRICE = "Normal fiyat sıfır veya daha büyük olmalıdır."
VAL_WEBSITE_PRICE = "Web sitesi fiyatı sıfır veya daha büyük olmalıdır."
VAL_MANAGER_VALUE = "Yönetici değeri sıfır veya daha büyük olmalıdır."
VAL_MANAGER_MODE_REQUIRED = "Birim fiyat veya satır toplam fiyatı seçin."
VAL_MANAGER_MODE_WITHOUT_VALUE = (
    "Yönetici modu, yönetici değeri olmadan verildi."
)
VAL_NO_LINES = "En az bir ürün satırı ekleyin."
VAL_NAME_REQUIRED = "Ürün adı zorunludur."

WARN_MANAGER_EXCEEDS = (
    "Yönetici satır toplamı, geçerli web sitesi toplamından yüksek. "
    "Değer girildiği gibi kullanılır."
)


def val_name_too_long(limit: int) -> str:
    return f"Ad en fazla {limit} karakter olmalıdır."


def _grouped(number: int) -> str:
    return f"{number:,}".replace(",", ".")


STOCK_NOT_WHOLE = "Adet bir tam sayı olmalıdır."
STOCK_NEGATIVE = "Adet negatif olamaz."
STOCK_ENTER_WHOLE = "Bir tam sayı girin."
STOCK_DIGITS_ONLY = "Yalnızca rakam kullanın (örneğin 12 gibi bir tam sayı)."


def stock_too_large(limit: int) -> str:
    return f"Adet {_grouped(limit)} değerini aşamaz."


# ======================================================================
# POS block
# ======================================================================

POS_LABEL = "POS giriş hesaplaması (kullanmadan önce doğrulayın)"
SEC_POS_DETAILS = "POS hesaplama ayrıntıları"

# ======================================================================
# Calculator presentation (application/calculator.py)
# ======================================================================

FIELD_PRODUCT_NAME_REQUIRED = "Bir ürün adı girin."


def exact_value_tooltip(exact: str) -> str:
    return f"Tam değer: {exact}"


LBL_QUANTITY = "Adet"
LBL_REGULAR_UNIT = "Normal fiyat (birim)"
LBL_WEBSITE_UNIT = "Web sitesi indirimli fiyatı (birim)"
LBL_REGULAR_TOTAL = "Normal fiyat toplamı"
LBL_WEBSITE_TOTAL = "Web sitesi indirimli toplam"
LBL_WEBSITE_DISCOUNTED_UNIT = "Web sitesi indirimli fiyatı (birim)"
LBL_WEBSITE_DISCOUNTED_TOTAL = "Web sitesi indirimli toplam"
LBL_GIFT = "Hediye"
NO_GIFT_NAME = "(hediye adı yok)"

SEC_PRICES = "Fiyatlar"
SEC_TEN = "Standart %10 senaryosu"
SEC_MANAGER = "Yönetici tarafından verilen değer"
SEC_WEBSITE_OPTION = "Web sitesi indirim seçeneği"
SEC_GIFT_OPTION = "Hediye seçeneği"
SEC_TOTALS = "İşlem toplamları"

LBL_DISCOUNT_BASE = "İndirim bazı"
VAL_BASE_REGULAR_GIFT = "Normal fiyat (hediye seçili)"
VAL_BASE_REGULAR = "Normal fiyat"
LBL_BASE_UNIT = "Baz (birim)"
LBL_TEN_DISCOUNT_UNIT = "%10 indirim (birim)"
LBL_TEN_RESULT_UNIT = "Sonuç birim fiyat"
LBL_TEN_RESULT_TOTAL = "Sonuç satır toplamı"

LBL_TEN_BASE = "%10 bazı"
LBL_TEN_BASE_UNIT = "%10 baz (birim)"
LBL_TEN_UNIT_PRICE = "%10 birim fiyat"
LBL_TEN_LINE_TOTAL = "%10 satır toplamı"

LBL_VALUE_MODE = "Değer modu"
MODE_LINE = "Satır toplam fiyatı"
MODE_UNIT = "Birim fiyat"
LBL_ENTERED_VALUE = "Girilen değer"
LBL_LINE_TOTAL = "Satır toplamı"
LBL_UNIT_VALUE = "Birim değer"
LBL_UNIT_VALUE_DERIVED = "Birim değer (türetilmiş, yalnızca gösterim)"
NOTE_MANAGER_SECTION = "Girildiği gibi kullanılır. Yüzdeye çevrilmez."

LBL_MANAGER_MODE = "Yönetici değer modu"
LBL_MANAGER_LINE_TOTAL = "Yönetici satır toplamı"
LBL_MANAGER_UNIT = "Yönetici birim değeri"
LBL_MANAGER_UNIT_DERIVED = (
    "Yönetici birim değeri (türetilmiş, yalnızca gösterim)"
)
LBL_MANAGER_VALUE = "Yönetici tarafından verilen değer"
VAL_SHOWN_ON_OTHER = "Diğer seçenekte gösteriliyor"
NOTE_MANAGER_OPTION = (
    "Yönetici değeri girildiği gibi kullanılır. Yüzdeye çevrilmez."
)
NOTE_GIFT_NOT_SELECTED = (
    "Bu satırda hediye seçili değil; karşılaştırma için gösteriliyor."
)

LBL_RESULT = "Sonuç"
POS_MISSING_MANAGER = "Yok: yönetici değeri girin"
LBL_POS_NORMAL_WEBSITE_TOTAL = "Normal web sitesi indirimli toplamı"
LBL_POS_AMOUNT = "POS giriş tutarı"
NOTE_POS = (
    "Yalnızca bilgilendirme amaçlıdır. Resmî veya yönetici onaylı bir POS talimatı değildir."
)

# transaction totals
LBL_LINES = "Satırlar"
LBL_TOTAL_REGULAR = "Normal fiyat toplamı"
LBL_TOTAL_WEBSITE = "Web sitesi indirimli toplam"
LBL_TOTAL_TEN = "Standart %10 senaryosu toplamı"
LBL_TOTAL_MANAGER = "Yönetici tarafından verilen toplam"
LBL_TOTAL_POS = "POS giriş toplamı"
MISSING_REGULAR = "normal fiyat"
MISSING_WEBSITE = "web sitesi fiyatı"
MISSING_PRICE = "fiyat"
MISSING_MANAGER = "yönetici değeri"
NOTE_TOTALS = (
    "Her satır kendi %10 bazını kullanır: hediyeli satırlarda normal fiyat, "
    "hediyesiz satırlarda web sitesi indirimli fiyatı."
)
NOTE_TOTAL_POS = (
    "Satır bazındaki POS giriş tutarlarının toplamıdır. Yalnızca bilgilendirme "
    "amaçlıdır. Resmî veya yönetici onaylı bir POS talimatı değildir."
)


def total_missing(what: str, line_numbers: str, several: bool) -> str:
    noun = "satırlar" if several else "satır"
    return f"{NOT_AVAILABLE}: {what} eksik ({noun} {line_numbers})"


PENDING_NO_LINES = "En az bir ürün satırı ekleyin."


def pending_lines(numbers: str) -> str:
    return (
        "Toplamlar, tüm satırlar geçerli olduğunda gösterilir. "
        f"Tamamlanacak veya düzeltilecek satırlar: {numbers}."
    )


# formula explanation (every line is generated from the LineResult)
EXPLAIN_BASE_REGULAR_GIFT = "normal fiyat (hediye seçili)"
EXPLAIN_BASE_WEBSITE_NOGIFT = "web sitesi indirimli fiyatı (hediyesiz)"
VAL_BASE_WEBSITE_NOGIFT = "Web sitesi indirimli fiyatı (hediye yok)"
VAL_BASE_WEBSITE = "Web sitesi indirimli fiyatı"


def explain_effective(website: str) -> str:
    return f"Web sitesi indirimli fiyatı = {website}"


def explain_ten_base(name: str, base: str) -> str:
    return f"%10 bazı = {name} = {base}"


def explain_ten_discount(base: str, discount: str) -> str:
    return f"%10 indirim = {base} × %10 = {discount}"


def explain_scenario_unit(base: str, discount: str, unit: str) -> str:
    return f"Senaryo birim fiyatı = {base} − {discount} = {unit}"


def explain_scenario_total(unit: str, quantity: int, total: str) -> str:
    return f"Senaryo satır toplamı = {unit} × {quantity} = {total}"


def explain_manager_line(line_total: str) -> str:
    return f"Yönetici satır toplamı = {line_total} (tüm satır için toplam olarak girildi)"


def explain_manager_unit_derived(
    line_total: str, quantity: int, unit: str
) -> str:
    return (
        f"Yönetici birim değeri = {line_total} ÷ {quantity} = {unit} "
        "(türetilmiştir; hesaplamalarda satır toplamı kullanılır)"
    )


def explain_manager_unit(unit: str, quantity: int, line_total: str) -> str:
    return f"Yönetici satır toplamı = {unit} × {quantity} = {line_total}"


def explain_pos(regular: str, website: str, manager: str, pos: str) -> str:
    return (
        f"POS giriş tutarı = ({regular} − {website}) + {manager} = {pos}"
    )


# ======================================================================
# History (application/history.py, ui/history_tab.py)
# ======================================================================

HISTORY_CORRUPT = "Kayıtlı hesaplama verisi okunamadı."
HISTORY_ONLY_COMPLETE = (
    "Yalnızca eksiksiz ve geçerli bir hesaplama kaydedilebilir."
)

SEC_AS_ENTERED = "Girildiği gibi"
NOTE_AS_ENTERED = (
    "Metin, yazıldığı gibi saklanır. Hesaplamada, başka yerde gösterilen "
    "normalleştirilmiş değerler kullanıldı."
)
LBL_ENTERED_QUANTITY = "Adet"
LBL_ENTERED_REGULAR = "Normal fiyat"
LBL_ENTERED_WEBSITE = "Web sitesi indirimli fiyatı"
LBL_ENTERED_MANAGER = "Yönetici tarafından verilen değer"
LBL_ENTERED_MANAGER_MODE = "Yönetici değer modu"


def confirmation_pos_unverified() -> str:
    return (
        f"{POS_LABEL}: bu hesaplama kaydedildiğinde POS giriş tutarları "
        "doğrulanmamış olarak gösterilmişti."
    )


def confirmation_other(state: str) -> str:
    return f"Kaydedildiğinde onay durumu: {state or 'bilinmiyor'}"


HISTORY_COLUMNS = (
    "Kayıt zamanı",
    "Ürünler",
    "Satır",
    "POS giriş toplamı (doğrulayın)",
)
BTN_LOAD_OLDER = "Eski hesaplamaları yükle"
HISTORY_NONE_YET = "Henüz kayıtlı hesaplama yok."
HISTORY_SELECT = "Ayrıntılarını görmek için kayıtlı bir hesaplama seçin."
HISTORY_GONE = "Bu hesaplama artık mevcut değil."
NOTE_HISTORY_FROZEN = (
    "Hesaplandığı ve kaydedildiği gibi gösterilir. Ürünlerde, fiyatlarda veya "
    "hediyelerde sonradan yapılan değişiklikler bunu etkilemez."
)
EXPLAIN_TITLE = "Bu nasıl hesaplandı"


def history_header(
    snapshot_id: int, saved_at: str, app_version: str, schema: int
) -> str:
    return (
        f"Kayıtlı hesaplama #{snapshot_id}\n"
        f"Kayıt: {saved_at} · uygulama {app_version} · şema {schema}"
    )


def history_footer(shown: int, total: int) -> str:
    return f"{total} kayıtlı hesaplamadan {shown} tanesi gösteriliyor"


# ======================================================================
# Calculator tab (ui/calculator_tab.py)
# ======================================================================

ONE_OFF_LABEL = "Tek seferlik ürün (aşağıya yazın)"
PH_REGULAR = "örneğin 5.000,00"
PH_WEBSITE = "örneğin 4.000,00"
PH_OPTIONAL = "isteğe bağlı"
CHK_GIFT = "Hediye dahil"
RADIO_UNIT = "Birim fiyat"
RADIO_LINE = "Satır toplam fiyatı"

FORM_PRODUCT = "Ürün"
FORM_NAME = "Ad"
FORM_QUANTITY = "Adet"
FORM_REGULAR = "Normal / ilk fiyat (birim)"
FORM_WEBSITE = "Web sitesi indirimli fiyatı (birim)"
FORM_GIFT_NAME = "Hediye adı"
FORM_MANAGER_VALUE = "Yönetici tarafından verilen değer"
FORM_MANAGER_MODE = "Yönetici değeri şudur"

TIP_MOVE_UP = "Satırı yukarı taşı"
TIP_MOVE_DOWN = "Satırı aşağı taşı"
TIP_REMOVE_LINE = "Satırı kaldır"
BTN_ADD_LINE = "Satır ekle"
BTN_SAVE_CALCULATION = "Hesaplamayı kaydet"
CARD_INCOMPLETE = (
    "Bu satırın sonuçlarını görmek için ürün adını ve fiyatları girin."
)
CARD_FIX = "Bu satırdaki vurgulanan alanları düzeltin."


def line_title(number: int) -> str:
    return f"Satır {number}"


def line_title_named(number: int, name: str) -> str:
    return f"Satır {number}: {name}"


# ======================================================================
# Products tab (ui/products_tab.py)
# ======================================================================

PRODUCT_HEADERS = (
    "Ad", "Normal fiyat", "Web sitesi indirimli fiyatı", "Varsayılan hediye", "Notlar",
    "Son güncelleme", "Sayılan adet", "Sayım zamanı",
)  # fmt: skip
TIP_COUNTED = (
    "Elle girilir veya depo sayımından içe aktarılır. Kendiliğinden değişmez ve "
    "resmî bir stok rakamı değildir."
)
DLG_ADD_PRODUCT = "Ürün ekle"
DLG_EDIT_PRODUCT = "Ürünü düzenle"
LBL_PRODUCT_NAME = "Ürün adı"
LBL_REGULAR_FIRST = "Normal / ilk fiyat"
LBL_WEBSITE_DISCOUNTED = "Web sitesi indirimli fiyatı"
LBL_DEFAULT_GIFT = "Varsayılan hediye (isteğe bağlı)"
LBL_NOTES = "Notlar (isteğe bağlı)"

PH_SEARCH = "Ürün adına göre ara"
CHK_SHOW_ARCHIVED = "Arşivlenenleri göster"
BTN_ADD_PRODUCT = "Ürün ekle"
BTN_EDIT = "Düzenle"
BTN_ARCHIVE = "Arşivle"
BTN_RESTORE = "Geri yükle"
BTN_UPDATE_QTY = "Adedi güncelle"
BTN_IMPORT_CSV = "CSV'den içe aktar"
CANNOT_CHANGE_TITLE = "Ürün değiştirilemiyor"

PH_QTY = "tam sayı, örneğin 12"
PH_QTY_NOTE = "isteğe bağlı, örneğin: depo fotoğrafı 24 Eki"
LBL_COUNTED_QTY = "Sayılan adet"
LBL_NOTE = "Not"
STOCK_NO_COUNT = "Bu ürün için henüz sayım kaydedilmedi."


def stock_title(name: str) -> str:
    return f"Adedi güncelle: {name}"


def stock_current(quantity: int, counted_at: str) -> str:
    return f"Şu an {quantity} (sayım: {counted_at})."


def stock_info(current: str) -> str:
    return (
        f"{current}\nDepo tarafından bildirilen sayıyı girin. Bu elle girilmiş bir "
        "kayıttır; canlı veya resmî stok değildir."
    )


# ======================================================================
# Import dialog (ui/import_dialog.py) and CSV import (infrastructure)
# ======================================================================

IMPORT_TITLE = "CSV'yi içe aktar"
IMPORT_COLUMNS = (
    "Satır", "Durum", "Ürün", "Normal fiyat", "Web sitesi fiyatı", "Adet",
    "Karar / notlar",
)  # fmt: skip
IMPORT_ERROR_COLUMNS = ("Satır", "Sütun", "Sorun")
STATUS_NEW = "Yeni"
STATUS_CONFLICT = "Çakışma"
STATUS_STOCK_UPDATE = "Adet güncellemesi"
STATUS_UNCHANGED = "Değişmedi"
FORMAT_PRICES = "Fiyat listesi (adet sütunu isteğe bağlı)"
FORMAT_STOCK = "Stok sayımları (ürün oluşturmaz)"
BTN_CHOOSE_CSV = "CSV dosyası seç…"
NO_FILE_CHOSEN = "Henüz dosya seçilmedi."
LBL_ROWS_WITH_ERRORS = "Hatalı satırlar"
CHK_VALID_ONLY = (
    "Yalnızca geçerli satırları içe aktar (hatalı satırları dışarıda bırak)"
)
BTN_APPLY_IMPORT = "İçe aktarmayı uygula"
FILE_DIALOG_TITLE = "Bir CSV dosyası seçin"
FILE_DIALOG_FILTER = "CSV dosyaları (*.csv);;Tüm dosyalar (*)"
COMBO_CHOOSE = "Seçin…"
COMBO_UPDATE = "Güncelle"
COMBO_UPDATE_RESTORE = "Güncelle ve geri yükle"
COMBO_SKIP = "Atla"
IMPORT_FIX_FILE = "Dosyayı düzeltin veya “Yalnızca geçerli satırları içe aktar” kutusunu işaretleyin."
IMPORT_DECIDE_ALL = "Her çakışma için Güncelle veya Atla seçin."
IMPORT_NOTHING = "İçe aktarılacak bir şey yok."
IMPORT_READY = "Hazır. İçe aktarma uygulanmadan önce yedek alınır."
IMPORT_BACKUP_FAILED_TITLE = "Yedekleme başarısız"
IMPORT_FAILED_TITLE = "İçe aktarma başarısız"
IMPORT_DONE_TITLE = "İçe aktarma tamamlandı"


def import_backup_failed(message: str) -> str:
    return f"{message}\n\nGüncel yedek olmadan içe aktarılsın mı?"


def import_counts(
    fmt: str, new: int, conflicts: int, stock: int, unchanged: int, errors: int
) -> str:
    return (
        f"{fmt}: {new} yeni · {conflicts} çakışma (her biri için karar verin) · "
        f"{stock} adet güncellemesi · {unchanged} değişmedi · {errors} hatalı satır"
    )


CSV_EXPECTED = (
    "Beklenen sütunlar: product_name,regular_price,website_discounted_price "
    "(ardından isteğe bağlı olarak quantity) veya stok sayımları için "
    "product_name,quantity."
)
CSV_DELIMITER = (
    "Dosya noktalı virgül veya sekme ile ayrılmış görünüyor. Dosyayı virgülle "
    "ayrılmış CSV olarak kaydedin ve virgül içeren fiyatları tırnak içine alın, "
    'örneğin "54.999,00".'
)
CSV_EMPTY = "Dosya boş."
CSV_NOT_UTF8 = "Dosya geçerli UTF-8 değil. “CSV UTF-8” olarak kaydedin."
CSV_EXTRA_CELLS = "Satırda başlıktan daha fazla hücre var. Virgül içeren değerleri tırnak içine alın."
CSV_NO_SUCH_PRODUCT = (
    "Bu adda bir ürün yok. Önce ürünü ekleyin; stok dosyaları ürün oluşturmaz."
)
CSV_ARCHIVED_STOCK = (
    "Bu ürün arşivlenmiş. Adedini güncellemeden önce geri yükleyin."
)


def csv_duplicate_header() -> str:
    return (
        "Geçersiz başlık: bir sütun adı birden fazla kez geçiyor. "
        + CSV_EXPECTED
    )


def csv_bad_header(missing: list[str], unknown: list[str]) -> str:
    problems: list[str] = []
    if missing:
        problems.append("eksik sütun(lar): " + ", ".join(missing))
    if unknown:
        problems.append("beklenmeyen sütun(lar): " + ", ".join(unknown))
    return "Geçersiz başlık: " + "; ".join(problems) + ". " + CSV_EXPECTED


def csv_ambiguous(column: str, text: str, read_as: str) -> str:
    return (
        f"{column}: '{text}', {read_as} olarak okundu (nokta binlik ayırıcı)"
    )


def csv_duplicate_row(first_row: int) -> str:
    return f"{first_row}. satırın kopyası (aynı ürün adı)."


def csv_not_valid(detail: str) -> str:
    return f"Dosya geçerli bir CSV değil: {detail}"


def csv_not_valid_near(line: int, detail: str) -> str:
    return f"Dosya geçerli bir CSV değil ({line}. satır civarı): {detail}"


def csv_too_many_rows(limit: int) -> str:
    return f"Çok fazla satır (sınır {_grouped(limit)})."


def csv_too_large(megabytes: int) -> str:
    return f"Dosya {megabytes} MB'tan büyük."


def csv_cannot_read(detail: str) -> str:
    return f"Dosya okunamadı: {detail}"


def import_summary_lines(
    created: int, updated: int, restored: int, stock_updated: int,
    skipped: int, unchanged: int, with_errors: int,
) -> tuple[str, ...]:  # fmt: skip
    out = [
        f"Yeni ürünler: {created}",
        f"Güncellenen fiyatlar: {updated}",
        f"Arşivden geri yüklenenler: {restored}",
        f"Güncellenen adetler: {stock_updated}",
        f"Sizin atladıklarınız: {skipped}",
        f"Değişmeyenler: {unchanged}",
    ]
    if with_errors:
        out.append(
            f"Hatalı olduğu için dışarıda bırakılan satırlar: {with_errors}"
        )
    return tuple(out)


def import_row_problem(row: int, name: str, message: str) -> str:
    return f"{row}. satır ({name}): {message}"


def import_row_no_plan(row: int) -> str:
    return f"{row}. satır: ürün planda yok."


def import_prices_missing(row: int, name: str) -> str:
    return f"{row}. satır ({name}): fiyatlar eksik."


def import_has_errors(count: int) -> str:
    return (
        f"Dosyada {count} satır hatası var. Dosyayı düzeltin veya yalnızca geçerli "
        "satırları içe aktarmayı seçin."
    )


def import_undecided(rows: str) -> str:
    return f"Her çakışma için Güncelle veya Atla seçin (satırlar {rows})."


def import_rolled_back(detail: str) -> str:
    return f"Hiçbir şey içe aktarılmadı. {detail}"


def import_db_error(detail: str) -> str:
    return f"Hiçbir şey içe aktarılmadı. Veritabanı hatası: {detail}"


# ======================================================================
# Repository / database / backups messages
# ======================================================================


def repo_duplicate(name: str) -> str:
    return f"'{name}' adlı etkin bir ürün zaten var."


def repo_not_found(product_id: int) -> str:
    return f"{product_id} numaralı ürün mevcut değil."


def repo_name_collision(name: str) -> str:
    return (
        f"Geri yüklenemiyor: '{name}' adlı etkin bir ürün zaten var. "
        "Birinin adını değiştirin veya birini arşivleyin."
    )


def db_cannot_open(detail: str) -> str:
    return f"Veritabanı açılamıyor: {detail}"


def db_schema_too_new(db_version: int, app_version: int) -> str:
    return (
        "Bu veritabanı, uygulamanın daha yeni bir sürümüyle oluşturulmuş "
        f"(şema {db_version}; bu sürüm en fazla {app_version} şemasını destekler). "
        "Uygulamayı güncelleyin. Veritabanında değişiklik yapılmadı."
    )


def db_migration_failed(version: int, name: str, detail: str) -> str:
    return f"{version:04d}_{name} geçişi başarısız oldu: {detail}"


def db_pre_migration_backup_failed(detail: str) -> str:
    return f"Geçiş öncesi yedekleme başarısız oldu: {detail}"


BACKUP_BUSY = "Bir veritabanı değişikliği sürüyor; birazdan tekrar deneyin."


def backup_verification_failed(detail: str) -> str:
    return f"Yedek kopyası doğrulamayı geçemedi: {detail}"


def backup_failed_create(detail: str) -> str:
    return f"Yedek oluşturulamadı: {detail}"


def backup_cannot_open_copy(detail: str) -> str:
    return f"kopya açılamadı: {detail}"


def backup_integrity(detail: str) -> str:
    return f"bütünlük denetimi şunu bildirdi: {detail}"


def backup_version_mismatch(found: int, expected: int) -> str:
    return f"şema sürümü {found}, canlı veritabanıyla ({expected}) eşleşmiyor"


# ======================================================================
# Settings tab and main window
# ======================================================================

LBL_DATABASE = "Veritabanı"
LBL_BACKUP_FOLDER = "Yedek klasörü"
BTN_OPEN_FOLDER = "Klasörü aç"
LBL_LATEST_BACKUP = "Son başarılı yedek"
BTN_BACKUP_NOW = "Şimdi yedekle"
BACKUPS_DISABLED = "Yedekleme etkin değil."
NO_BACKUP_YET = "Henüz yedek yok."

BACKUP_REASON_LABELS = {
    "baseline": "ilk yedek",
    "startup": "başlangıç",
    "close": "kapanış",
    "pre_migration": "yükseltme öncesi",
    "pre_import": "içe aktarma öncesi",
    "manual": "elle",
}
BACKUP_REASON_UNKNOWN = "bilinmiyor"


def settings_disk_note(keep: int) -> str:
    return (
        "Yedekler veritabanıyla aynı diskte saklanır, bu nedenle disk arızasına karşı "
        f"koruma sağlamaz. En yeni {keep} doğrulanmış yedek tutulur."
    )


def latest_backup_line(when: str, reason: str, name: str) -> str:
    return f"{when} · {reason} · {name}"


def backup_count(count: int) -> str:
    return f"Yedek klasöründe {count} doğrulanmış yedek var."


def backup_ok(name: str) -> str:
    return f"Yedek oluşturuldu ve doğrulandı: {name}"


def backup_failed(message: str) -> str:
    return f"Yedekleme başarısız: {message}"


def describe_backup_failure(reason: str, when: str, message: str) -> str:
    return f"Son yedekleme ({reason}, {when}) başarısız oldu: {message}"


def backup_banner(description: str) -> str:
    return (
        f"⚠ {description} Son değişiklikler yedeklenmemiş olabilir. "
        "Ayarlar sekmesini açıp “Şimdi yedekle” düğmesini seçin."
    )


TAB_PRODUCTS = "Ürünler"
TAB_CALCULATOR = "Hesaplayıcı"
TAB_HISTORY = "Geçmiş"
TAB_SETTINGS = "Ayarlar"

BACKUP_CLOSE_FAILED_TITLE = "Kapanışta yedekleme başarısız"


def backup_close_failed(message: str) -> str:
    return (
        f"{message}\n\nUygulama yine de kapanacak. Uygulamayı yeniden başlatın ve "
        "Ayarlar'daki “Şimdi yedekle” düğmesini kullanın."
    )


CALC_NOT_SAVED_TITLE = "Hesaplama kaydedilmedi"


def calc_save_failed(detail: str) -> str:
    return f"Hesaplama kaydedilemedi: {detail}"


def calc_saved_status(snapshot_id: int) -> str:
    return f"#{snapshot_id} numaralı hesaplama geçmişe kaydedildi."


# ======================================================================
# Start-up (main.py)
# ======================================================================

UNEXPECTED_ERROR_TITLE = "Beklenmeyen hata"
CANNOT_START_TITLE = "Başlatılamıyor"
CANNOT_OPEN_DB_TITLE = "Veritabanı açılamıyor"


def unexpected_error(detail: object, log_path: object) -> str:
    return f"Beklenmeyen bir hata oluştu:\n{detail}\n\nAyrıntılar şuraya yazıldı:\n{log_path}"


def cannot_create_data_dir(detail: object) -> str:
    return f"Veri klasörü oluşturulamıyor:\n{detail}"
