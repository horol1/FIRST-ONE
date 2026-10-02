"""Load the Data sheet from Sales.xlsx into sales.db."""
from __future__ import annotations

import sqlite3
import zipfile
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parent
XLSX = ROOT / "Sales.xlsx"
DB = ROOT / "sales.db"
NS = "{http://schemas.openxmlformats.org/spreadsheetml/2006/main}"
EXCEL_EPOCH = datetime(1899, 12, 30)
COLUMNS = [
    "date",
    "day",
    "month",
    "year",
    "customer_age",
    "age_group",
    "customer_gender",
    "country",
    "state",
    "product_category",
    "sub_category",
    "product",
    "order_quantity",
    "unit_cost",
    "unit_price",
    "profit",
    "cost",
    "revenue",
]


def col_index(cell_ref: str) -> int:
    letters = "".join(ch for ch in cell_ref if ch.isalpha())
    n = 0
    for ch in letters:
        n = n * 26 + (ord(ch.upper()) - 64)
    return n - 1


def excel_date(value: str) -> str:
    days = int(float(value))
    return (EXCEL_EPOCH + timedelta(days=days)).strftime("%Y-%m-%d")


def load_shared_strings(zf: zipfile.ZipFile) -> list[str]:
    root = ET.fromstring(zf.read("xl/sharedStrings.xml"))
    strings = []
    for si in root.findall(f"{NS}si"):
        strings.append("".join((t.text or "") for t in si.findall(f".//{NS}t")))
    return strings


def cell_value(cell, shared: list[str]):
    value = cell.findtext(f"{NS}v")
    if value is None:
        return None
    if cell.get("t") == "s":
        return shared[int(value)]
    return value


def to_int(value):
    if value in (None, ""):
        return None
    return int(float(value))


def to_float(value):
    if value in (None, ""):
        return None
    return float(value)


def row_tuple(values: list):
    date = excel_date(values[0]) if values[0] not in (None, "") else None
    return (
        date,
        to_int(values[1]),
        values[2],
        to_int(values[3]),
        to_int(values[4]),
        values[5],
        values[6],
        values[7],
        values[8],
        values[9],
        values[10],
        values[11],
        to_int(values[12]),
        to_float(values[13]),
        to_float(values[14]),
        to_float(values[15]),
        to_float(values[16]),
        to_float(values[17]),
    )


def main() -> None:
    if not XLSX.exists():
        raise SystemExit(f"Missing {XLSX.name}")

    if DB.exists():
        DB.unlink()

    print("Reading Sales.xlsx ...")
    with zipfile.ZipFile(XLSX) as zf:
        shared = load_shared_strings(zf)
        source = zf.open("xl/worksheets/sheet5.xml")
        db = sqlite3.connect(DB)
        db.execute("PRAGMA journal_mode = OFF")
        db.execute("PRAGMA synchronous = OFF")
        db.execute(
            """
            CREATE TABLE sales (
              id INTEGER PRIMARY KEY,
              date TEXT,
              day INTEGER,
              month TEXT,
              year INTEGER,
              customer_age INTEGER,
              age_group TEXT,
              customer_gender TEXT,
              country TEXT,
              state TEXT,
              product_category TEXT,
              sub_category TEXT,
              product TEXT,
              order_quantity INTEGER,
              unit_cost REAL,
              unit_price REAL,
              profit REAL,
              cost REAL,
              revenue REAL
            )
            """
        )

        insert = db.executemany
        sql = f"INSERT INTO sales ({', '.join(COLUMNS)}) VALUES ({', '.join('?' * len(COLUMNS))})"
        batch = []
        count = 0

        try:
            for event, elem in ET.iterparse(source, events=("end",)):
                if elem.tag != f"{NS}row":
                    continue
                row_num = int(elem.get("r", "0"))
                if row_num == 1:
                    elem.clear()
                    continue

                values = [None] * 18
                for cell in elem.findall(f"{NS}c"):
                    idx = col_index(cell.get("r", "A"))
                    if idx > 17:
                        continue
                    values[idx] = cell_value(cell, shared)

                if values[0] is None:
                    elem.clear()
                    continue

                batch.append(row_tuple(values))
                if len(batch) >= 5000:
                    insert(sql, batch)
                    count += len(batch)
                    print(f"  imported {count:,} rows", flush=True)
                    batch.clear()
                elem.clear()
        finally:
            source.close()

        if batch:
            insert(sql, batch)
            count += len(batch)

        print("Indexing ...")
        db.execute("CREATE INDEX idx_sales_year ON sales(year)")
        db.execute("CREATE INDEX idx_sales_country ON sales(country)")
        db.execute("CREATE INDEX idx_sales_category ON sales(product_category)")
        db.commit()
        db.close()

    print(f"Done. {count:,} rows saved to {DB.name}")


if __name__ == "__main__":
    main()
