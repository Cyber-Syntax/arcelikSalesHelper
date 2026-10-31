from decimal import Decimal

from arcelikSalesHelper.infrastructure.scrape_report import (
    ReportRow,
    write_report_csv,
)

from arcelikSalesHelper import strings as T


def test_report_csv_bom_columns_and_escaping(tmp_path):
    path = tmp_path / "r.csv"
    rows = [
        ReportRow("ADE 500", T.UPDATE_STATUS_UPDATED,
                  Decimal(100), Decimal(120), Decimal(0), Decimal(110)),
        ReportRow("=EVIL()", T.UPDATE_STATUS_CREATED, None, Decimal(5), None, Decimal(0)),
    ]  # fmt: skip
    assert write_report_csv(rows, path) == 2
    raw = path.read_bytes()
    assert raw.startswith(b"\xef\xbb\xbf")
    lines = raw.decode("utf-8-sig").splitlines()
    assert lines[0] == (
        "product_name,status,old_regular_price,new_regular_price,"
        "old_website_price,new_website_price"
    )
    assert lines[1] == "ADE 500,Güncellendi,100,120,0,110"
    assert lines[2].startswith("'=EVIL()")
    assert lines[2].endswith(",Yeni eklendi,,5,,0")
