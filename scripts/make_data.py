"""Generate the seed data, the invoice PDFs and the labelled samples that are produced from code.

    python scripts/make_data.py

Deterministic (fixed random seed), so re-running it gives byte-identical files. The hand-written samples
(lead-intake, support-triage, content-repurpose) live in data/samples as JSON and are not touched here.
"""

from __future__ import annotations

import csv
import json
import random
import sys
from collections import defaultdict
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from opsflow.kpi import compute_kpis  # noqa: E402

SEED = ROOT / "data" / "seed"
SAMPLES = ROOT / "data" / "samples"
INVOICES = ROOT / "data" / "invoices"


def dump(path: Path, data: object) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=1, ensure_ascii=False) + "\n", encoding="utf-8")


# ------------------------------------------------------------------------------------------------------- CRM

CRM = [
    ("Kate Whitfield", "Kaimai Adventure Store", "kate.whitfield@example.com", "021 555 0101", "wholesale"),
    ("Tomasi Fifita", "Harbourside Rowing Club", "tomasi.fifita@example.com", "022 555 0102", "club_or_school"),
    ("Rebecca Shaw", "Northcote Scouts", "rebecca.shaw@example.com", "027 555 0103", "club_or_school"),
    ("Ben Carver", "Carver Events Ltd", "ben.carver@example.com", "09 555 0104", "sponsorship_or_partnership"),
    ("Mere Tane", "Te Aroha Outdoors", "mere.tane@example.com", "021 555 0105", "wholesale"),
    ("Lucy Ng", "Ng & Partners Accounting", "lucy.ng@example.com", "021 555 0106", "corporate_bulk"),
    ("Sam O'Brien", "", "sam.obrien@example.com", "022 555 0107", "retail_customer"),
    ("Grace Liu", "Summit School", "grace.liu@example.com", "03 555 0108", "club_or_school"),
]


def make_crm() -> None:
    rows = [
        {
            "id": f"C{i:04d}",
            "name": name,
            "company": company,
            "email": email,
            "phone": phone,
            "category": category,
            "priority": "warm",
            "source": "existing customer",
            "owner": "Sales team",
            "seed": True,
        }
        for i, (name, company, email, phone, category) in enumerate(CRM, start=1)
    ]
    dump(SEED / "crm_contacts.json", rows)


# -------------------------------------------------------------------------------------------------- suppliers

SUPPLIERS = [
    {
        "supplier_id": "SUP-01",
        "name": "Southern Alps Textiles Ltd",
        "gst_number": "112-345-678",
        "currency": "NZD",
        "country": "NZ",
        "terms_days": 20,
        "layout": "A",
        "prefix": "SAT-",
    },
    {
        "supplier_id": "SUP-02",
        "name": "Kauri Coast Packaging Ltd",
        "gst_number": "98-765-432",
        "currency": "NZD",
        "country": "NZ",
        "terms_days": 30,
        "layout": "B",
        "prefix": "KCP",
    },
    {
        "supplier_id": "SUP-03",
        "name": "Tasman Trail Footwear Ltd",
        "gst_number": "123-456-789",
        "currency": "NZD",
        "country": "NZ",
        "terms_days": 30,
        "layout": "C",
        "prefix": "TTF/",
    },
    {
        "supplier_id": "SUP-04",
        "name": "Ridgeline Camp Supplies Ltd",
        "gst_number": "104-221-907",
        "currency": "NZD",
        "country": "NZ",
        "terms_days": 20,
        "layout": "A",
        "prefix": "RCS-",
    },
    {
        "supplier_id": "SUP-05",
        "name": "Harbour Freight Logistics Ltd",
        "gst_number": "116-532-004",
        "currency": "NZD",
        "country": "NZ",
        "terms_days": 14,
        "layout": "B",
        "prefix": "HFL-",
    },
    {
        "supplier_id": "SUP-06",
        "name": "Bluegum Outdoor Pty Ltd",
        "gst_number": "",
        "currency": "AUD",
        "country": "AU",
        "terms_days": 30,
        "layout": "C",
        "prefix": "BGO",
    },
]
UNKNOWN = {
    "Coastline Promo Products Ltd": {"gst_number": "131-777-210", "layout": "A", "prefix": "CPP-", "terms_days": 20},
    "Peak Performance Apparel Ltd": {"gst_number": "125-640-388", "layout": "B", "prefix": "PPA", "terms_days": 30},
}

# invoice spec: id, split, supplier, invoice number suffix, date, po, lines, fault
# fault: None | gst | total | dup | po | lines
INVOICE_SPECS = [
    (
        "I01",
        "dev",
        "Southern Alps Textiles Ltd",
        "10477",
        "2026-09-02",
        "PO-2026-0141",
        [("Ripstop nylon 70D, forest green (m)", 120, 8.40), ("Seam tape 20 mm (roll)", 15, 12.00)],
        None,
    ),
    (
        "I02",
        "dev",
        "Kauri Coast Packaging Ltd",
        "50213",
        "2026-09-03",
        "PO-2026-0143",
        [("Courier bags A3 (pack of 500)", 6, 74.50), ("Shipping boxes medium (bundle of 50)", 10, 61.20)],
        None,
    ),
    (
        "I03",
        "dev",
        "Tasman Trail Footwear Ltd",
        "8812",
        "2026-09-04",
        "PO-2026-0144",
        [("Summit hiking boot, sizes 38-46", 36, 96.00)],
        None,
    ),
    (
        "I04",
        "dev",
        "Ridgeline Camp Supplies Ltd",
        "3307",
        "2026-09-05",
        "PO-2026-0145",
        [("Self-inflating sleeping mat", 40, 38.75), ("Stuff sack 10 L", 40, 6.10)],
        "gst",
    ),
    (
        "I05",
        "dev",
        "Harbour Freight Logistics Ltd",
        "2350",
        "2026-09-07",
        None,
        [("Linehaul Auckland-Wellington, pallets", 6, 145.00), ("Fuel surcharge", 1, 62.40)],
        "total",
    ),
    (
        "I06",
        "dev",
        "Coastline Promo Products Ltd",
        "0091",
        "2026-09-08",
        None,
        [("Branded lanyards", 500, 1.35), ("Setup fee", 1, 85.00)],
        None,
    ),
    (
        "I07",
        "dev",
        "Southern Alps Textiles Ltd",
        "10388",
        "2026-09-09",
        "PO-2026-0131",
        [("Polar fleece 300 gsm, charcoal (m)", 80, 11.90)],
        "dup",
    ),
    (
        "I08",
        "dev",
        "Bluegum Outdoor Pty Ltd",
        "4471",
        "2026-09-10",
        "PO-2026-0146",
        [("Hydration bladder 2 L", 150, 9.80), ("Bite valve spare", 150, 1.20)],
        None,
    ),
    (
        "I09",
        "dev",
        "Kauri Coast Packaging Ltd",
        "50240",
        "2026-09-11",
        "PO-2026-0147",
        [("Recycled tissue paper (ream)", 30, 22.00), ("Printed swing tags (1,000)", 4, 96.00)],
        "po",
    ),
    (
        "I10",
        "dev",
        "Tasman Trail Footwear Ltd",
        "8839",
        "2026-09-14",
        None,
        [("Gaiters, waterproof, pair", 50, 18.40), ("Boot laces 150 cm, pair", 100, 1.90)],
        None,
    ),
    (
        "I11",
        "dev",
        "Ridgeline Camp Supplies Ltd",
        "3321",
        "2026-09-15",
        "PO-2026-0149",
        [("Aluminium tent pegs (pack of 10)", 80, 7.20), ("Guy rope 4 mm (20 m)", 60, 5.50)],
        "lines",
    ),
    (
        "I12",
        "dev",
        "Harbour Freight Logistics Ltd",
        "2377",
        "2026-09-16",
        None,
        [("Courier, North Island zone", 210, 6.80)],
        None,
    ),
    (
        "I13",
        "dev",
        "Southern Alps Textiles Ltd",
        "10502",
        "2026-09-17",
        "PO-2026-0150",
        [
            ("Ripstop nylon 70D, ochre (m)", 90, 8.40),
            ("YKK zip #5, 60 cm", 200, 1.15),
            ("Webbing 25 mm (m)", 300, 0.62),
            ("Side-release buckle 25 mm", 300, 0.48),
            ("Seam tape 20 mm (roll)", 10, 12.00),
        ],
        None,
    ),
    (
        "I14",
        "dev",
        "Tasman Trail Footwear Ltd",
        "8851",
        "2026-09-18",
        "PO-2026-0151",
        [("Trail runner, sizes 36-45", 24, 88.00)],
        "gst",
    ),
    (
        "I15",
        "dev",
        "Kauri Coast Packaging Ltd",
        "50262",
        "2026-09-21",
        None,
        [("Courier bags A2 (pack of 250)", 8, 69.90)],
        None,
    ),
    (
        "I16",
        "dev",
        "Ridgeline Camp Supplies Ltd",
        "3340",
        "2026-09-22",
        None,
        [("Camp mug, enamel", 120, 4.25), ("Spork, titanium", 120, 3.10)],
        None,
    ),
    (
        "I17",
        "heldout",
        "Southern Alps Textiles Ltd",
        "10531",
        "2026-09-23",
        "PO-2026-0153",
        [("Merino jersey 200 gsm, navy (m)", 60, 21.50), ("Ribbing 1x1 (m)", 25, 9.80)],
        None,
    ),
    (
        "I18",
        "heldout",
        "Kauri Coast Packaging Ltd",
        "50288",
        "2026-09-24",
        "PO-2026-0154",
        [("Shipping boxes large (bundle of 50)", 12, 79.00)],
        "gst",
    ),
    (
        "I19",
        "heldout",
        "Peak Performance Apparel Ltd",
        "7720",
        "2026-09-25",
        None,
        [("Performance tee samples", 30, 19.50)],
        None,
    ),
    (
        "I20",
        "heldout",
        "Tasman Trail Footwear Ltd",
        "8870",
        "2026-09-28",
        "PO-2026-0156",
        [("Summit hiking boot, sizes 38-46", 18, 96.00), ("Insoles, cushioned", 40, 9.40)],
        None,
    ),
    (
        "I21",
        "heldout",
        "Harbour Freight Logistics Ltd",
        "2291",
        "2026-09-29",
        None,
        [("Linehaul Auckland-Christchurch, pallets", 4, 210.00)],
        "dup",
    ),
    (
        "I22",
        "heldout",
        "Bluegum Outdoor Pty Ltd",
        "4502",
        "2026-09-30",
        None,
        [("Collapsible water bottle 1 L", 200, 6.40)],
        None,
    ),
    (
        "I23",
        "heldout",
        "Ridgeline Camp Supplies Ltd",
        "3366",
        "2026-10-01",
        "PO-2026-0158",
        [("Dome tent poles, spare set", 30, 27.50), ("Pole repair sleeve", 60, 2.20)],
        "total",
    ),
    (
        "I24",
        "heldout",
        "Southern Alps Textiles Ltd",
        "10560",
        "2026-10-02",
        "PO-2026-0159",
        [("Polar fleece 300 gsm, forest (m)", 140, 11.90)],
        "po",
    ),
]

SEED_BILLS = [
    ("SUP-01", "Southern Alps Textiles Ltd", "SAT-10388", "2026-08-28", 952.00),
    ("SUP-05", "Harbour Freight Logistics Ltd", "HFL-2291", "2026-09-01", 840.00),
    ("SUP-02", "Kauri Coast Packaging Ltd", "KCP50190", "2026-08-25", 1210.40),
]


def money(x: float) -> str:
    return f"{x:,.2f}"


def long_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def nz_date(iso: str) -> str:
    d = date.fromisoformat(iso)
    return d.strftime("%d/%m/%Y")


def due_date(iso: str, terms: int) -> str:
    d = date.fromisoformat(iso)
    if terms == 20:  # 20th of the month following
        nxt = (d.replace(day=1) + timedelta(days=32)).replace(day=20)
        return nxt.isoformat()
    return (d + timedelta(days=terms)).isoformat()


class Invoice(FPDF):
    pass


def render_invoice(inv: dict, layout: str, out: Path) -> None:
    pdf = Invoice(format="A4")
    pdf.set_auto_page_break(False)
    pdf.set_creation_date(datetime(2026, 9, 1, tzinfo=UTC))  # fixed, so rebuilding gives identical files
    pdf.add_page()
    pdf.set_margins(18, 18)
    cur = inv["currency"]
    lines = inv["lines"]

    def row(cells: list[tuple[str, float, str]], h: float = 7, bold: bool = False) -> None:
        pdf.set_font("Helvetica", "B" if bold else "", 10)
        for text, w, align in cells:
            pdf.cell(w, h, text, align=align)
        pdf.ln(h)

    if layout == "A":
        pdf.set_font("Helvetica", "B", 18)
        pdf.cell(0, 10, inv["supplier_name"], new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"GST number: {inv['gst_number']}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        pdf.set_font("Helvetica", "B", 14)
        pdf.cell(0, 8, "TAX INVOICE", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        for label, value in (
            ("Invoice number:", inv["invoice_number"]),
            ("Invoice date:", nz_date(inv["invoice_date"])),
            ("Due date:", nz_date(inv["due_date"])),
            ("Your PO:", inv["po_number"] or "-"),
            ("Bill to:", "Acme Outdoor Gear Ltd, 14 Quay Street, Auckland"),
        ):
            row([(label, 35, "L"), (value, 120, "L")], 6)
        pdf.ln(4)
        row([("Description", 90, "L"), ("Qty", 20, "R"), ("Unit price", 30, "R"), ("Amount", 34, "R")], bold=True)
        for desc, qty, unit, amount in lines:
            row([(desc, 90, "L"), (str(qty), 20, "R"), (money(unit), 30, "R"), (money(amount), 34, "R")])
        pdf.ln(3)
        for label, value in (("Subtotal", inv["subtotal"]), ("GST 15%", inv["gst"]), (f"Total {cur}", inv["total"])):
            row([("", 110, "L"), (label, 30, "R"), (money(value), 34, "R")], bold=label.startswith("Total"))
        pdf.ln(6)
        pdf.set_font("Helvetica", "", 9)
        pdf.multi_cell(
            0, 5, "Payment by direct credit. Please quote the invoice number.", new_x="LMARGIN", new_y="NEXT"
        )
    elif layout == "B":
        pdf.set_font("Helvetica", "", 9)
        pdf.cell(0, 5, f"{inv['supplier_name']}  |  GST Reg. No. {inv['gst_number']}", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(6)
        pdf.set_font("Helvetica", "B", 16)
        pdf.cell(0, 9, "Invoice", new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        pdf.cell(0, 6, f"Invoice No. {inv['invoice_number']}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Date of issue {long_date(inv['invoice_date'])}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, f"Payment due {long_date(inv['due_date'])}", new_x="LMARGIN", new_y="NEXT")
        if inv["po_number"]:
            pdf.cell(0, 6, f"Order reference {inv['po_number']}", new_x="LMARGIN", new_y="NEXT")
        pdf.cell(0, 6, "Customer: Acme Outdoor Gear Ltd", new_x="LMARGIN", new_y="NEXT")
        pdf.ln(4)
        row([("Item", 100, "L"), ("Quantity", 22, "R"), ("Rate", 26, "R"), ("Line total", 26, "R")], bold=True)
        for desc, qty, unit, amount in lines:
            row([(desc, 100, "L"), (str(qty), 22, "R"), (money(unit), 26, "R"), (money(amount), 26, "R")])
        pdf.ln(3)
        for label, value in (
            ("Total excl. GST", inv["subtotal"]),
            ("GST @ 15%", inv["gst"]),
            ("Amount payable", inv["total"]),
        ):
            row([("", 100, "L"), (label, 48, "R"), (f"${money(value)}", 26, "R")], bold=label == "Amount payable")
    else:  # C: compact, prose-like layout
        pdf.set_font("Helvetica", "B", 13)
        pdf.cell(0, 8, inv["supplier_name"].upper(), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font("Helvetica", "", 10)
        reg = f"GST {inv['gst_number']}" if inv["gst_number"] else "ABN 51 824 753 556 (Australia)"
        pdf.multi_cell(
            0,
            5,
            f"{reg}. Invoice {inv['invoice_number']} issued {long_date(inv['invoice_date'])} to Acme Outdoor Gear Ltd"
            f"{', against order ' + inv['po_number'] if inv['po_number'] else ''}. "
            f"Please pay by {long_date(inv['due_date'])}.",
            new_x="LMARGIN",
            new_y="NEXT",
        )
        pdf.ln(3)
        for desc, qty, unit, amount in lines:
            text = f"- {qty} x {desc} @ {money(unit)} = {money(amount)}"
            pdf.multi_cell(0, 5, text, new_x="LMARGIN", new_y="NEXT")
        pdf.ln(3)
        gst_label = "GST (15%)" if cur == "NZD" else "GST not applicable (export)"
        pdf.multi_cell(
            0,
            5,
            f"Sub-total {money(inv['subtotal'])}   {gst_label} {money(inv['gst'])}   "
            f"TOTAL {cur} {money(inv['total'])}",
            new_x="LMARGIN",
            new_y="NEXT",
        )
    out.parent.mkdir(parents=True, exist_ok=True)
    pdf.output(str(out))


def make_invoices() -> None:
    by_name = {s["name"]: s for s in SUPPLIERS}
    items = []
    purchase_orders = []
    for spec in INVOICE_SPECS:
        sid, split, supplier, suffix, inv_date, po, raw_lines, fault = spec
        known = by_name.get(supplier)
        info = known or {"name": supplier, **UNKNOWN[supplier], "currency": "NZD", "supplier_id": None}
        currency = info["currency"]
        lines = [(d, q, u, round(q * u, 2)) for d, q, u in raw_lines]
        subtotal = round(sum(line[3] for line in lines), 2)
        gst = round(subtotal * 0.15, 2) if currency == "NZD" else 0.0
        reasons: list[str] = []
        printed_subtotal = subtotal
        if fault == "gst":
            gst = round(subtotal * 0.10, 2)
            reasons.append("gst_mismatch")
        total = round(printed_subtotal + gst, 2)
        if fault == "total":
            total = round(total + 90.0, 2)
            reasons.append("total_mismatch")
        if fault == "lines":
            printed_subtotal = round(subtotal + 64.0, 2)
            gst = round(printed_subtotal * 0.15, 2)
            total = round(printed_subtotal + gst, 2)
            reasons.append("lines_mismatch")
        if known is None:
            reasons.append("unknown_supplier")
        if fault == "dup":
            reasons.append("duplicate_invoice")
        if po:
            po_amount = round(printed_subtotal * (0.8 if fault == "po" else 1.0), 2)
            purchase_orders.append(
                {
                    "po_number": po,
                    "supplier_id": info["supplier_id"],
                    "supplier_name": supplier,
                    "amount_excl_gst": po_amount,
                    "currency": currency,
                    "status": "open",
                    "seed": True,
                }
            )
            if fault == "po":
                reasons.append("po_mismatch")
        number = f"{info['prefix']}{suffix}"
        inv = {
            "supplier_name": supplier,
            "gst_number": info["gst_number"] or None,
            "invoice_number": number,
            "invoice_date": inv_date,
            "due_date": due_date(inv_date, info["terms_days"]),
            "po_number": po,
            "currency": currency,
            "lines": lines,
            "subtotal": printed_subtotal,
            "gst": gst,
            "total": total,
        }
        filename = f"{sid}-{number.replace('/', '-').lower()}.pdf"
        render_invoice(inv, info["layout"], INVOICES / filename)
        expected = {k: v for k, v in inv.items() if k != "lines"}
        expected.update(
            {
                "route": "exception" if reasons else "draft_bill",
                "reasons": reasons,
                "line_count": len(lines),
                "layout": info["layout"],
            }
        )
        items.append(
            {
                "id": sid,
                "split": split,
                "input": {
                    "message_id": f"<{sid.lower()}@mail.example.com>",
                    "from": f"accounts@{'example.com'}",
                    "subject": f"Invoice {number} from {supplier}",
                    "attachment_name": filename,
                    "attachment_path": f"/files/invoices/{filename}",
                },
                "expected": expected,
            }
        )
    dump(SEED / "purchase_orders.json", purchase_orders)
    suppliers = [{k: v for k, v in s.items() if k not in ("layout", "prefix")} | {"seed": True} for s in SUPPLIERS]
    dump(SEED / "suppliers.json", suppliers)
    bills = [
        {
            "id": f"BILL-{i:04d}",
            "supplier_id": sid,
            "supplier_name": name,
            "invoice_number": num,
            "invoice_date": d,
            "total": total,
            "currency": "NZD",
            "status": "AUTHORISED",
            "seed": True,
        }
        for i, (sid, name, num, d, total) in enumerate(SEED_BILLS, start=1)
    ]
    dump(SEED / "bills.json", bills)
    dump(
        SAMPLES / "supplier-invoice.json",
        {
            "workflow": "supplier-invoice",
            "description": "Invented supplier invoices as PDFs in three layouts (A: table, B: alternative labels and "
            "long dates, C: prose-like). Labels: every header field, the route (draft_bill or exception) and the "
            "exception reasons. Items marked heldout were never used while tuning prompts or rules.",
            "items": items,
        },
    )


# ------------------------------------------------------------------------------------------------------ sales

PRODUCTS = [
    ("PK-TH45", "Trailhead 45L pack", "packs", 249.0),
    ("PK-TH55", "Trailhead 55L pack", "packs", 299.0),
    ("PK-KEA", "Kea daypack 22L", "packs", 119.0),
    ("TN-KEA2", "Kea 3-season tent", "tents", 449.0),
    ("SB-ALP0", "Alpine 0 sleeping bag", "sleeping", 329.0),
    ("SM-SI", "Self-inflating sleeping mat", "sleeping", 129.0),
    ("JK-FIO", "Fiordland rain jacket", "clothing", 329.0),
    ("BL-M200", "Merino 200 base layer", "clothing", 119.0),
    ("ST-EMB2", "Ember 2 stove", "cooking", 89.0),
    ("DB-INS", "Insulated drink bottle 750 ml", "accessories", 44.9),
    ("HL-LUM", "Lumen headlamp", "accessories", 79.0),
    ("GT-WP", "Waterproof gaiters", "accessories", 59.0),
]
WEIGHTS = [8, 6, 9, 3, 4, 6, 5, 8, 7, 12, 9, 5]


def make_sales() -> list[dict]:
    rng = random.Random(2026)
    rows: list[dict] = []
    start, end = date(2026, 8, 1), date(2026, 9, 30)
    n = 0
    d = start
    while d <= end:
        iso = d.isoformat()
        weekend = d.weekday() >= 5
        online = rng.randint(24, 38)
        store = rng.randint(22, 34) if weekend else rng.randint(14, 24)
        wholesale = 0 if weekend else rng.randint(0, 2)
        refund_p = 0.025
        if iso == "2026-09-12":  # online checkout outage
            online = 4
        if iso == "2026-09-15":  # refund spike after a faulty batch
            refund_p = 0.14
        if iso == "2026-09-22":  # big wholesale day
            wholesale = 6
        if iso == "2026-09-29":  # store point-of-sale outage
            store = 0
        for channel, count in (("online", online), ("store", store), ("wholesale", wholesale)):
            for _ in range(count):
                n += 1
                sku, name, cat, price = rng.choices(PRODUCTS, weights=WEIGHTS)[0]
                if channel == "wholesale":
                    qty = rng.randint(8, 30)
                    unit = round(price * 0.55, 2)
                else:
                    qty = 1 if rng.random() < 0.8 else 2
                    unit = price
                status = "refunded" if channel != "wholesale" and rng.random() < refund_p else "paid"
                rows.append(
                    {
                        "order_id": f"A{n:05d}",
                        "order_date": iso,
                        "channel": channel,
                        "sku": sku,
                        "product": name,
                        "category": cat,
                        "qty": qty,
                        "unit_price": f"{unit:.2f}",
                        "total_nzd": f"{qty * unit:.2f}",
                        "status": status,
                    }
                )
        d += timedelta(days=1)
    with (SEED / "sales_orders.csv").open("w", encoding="utf-8", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    return rows


def make_kpi_samples(rows: list[dict]) -> None:
    by_date: dict[str, list[dict]] = defaultdict(list)
    for r in rows:
        by_date[r["order_date"]].append(r)
    items = []
    d = date(2026, 9, 10)
    while d <= date(2026, 9, 30):
        iso = d.isoformat()
        prev = (d - timedelta(days=7)).isoformat()
        k = compute_kpis(by_date[iso], by_date[prev])
        items.append(
            {
                "id": f"K{d.day:02d}",
                "split": "dev" if d <= date(2026, 9, 23) else "heldout",
                "input": {"report_date": iso},
                "expected": k,
            }
        )
        d += timedelta(days=1)
    dump(
        SAMPLES / "kpi-digest.json",
        {
            "workflow": "kpi-digest",
            "description": "Report dates for the daily KPI digest. Expected KPIs and alerts are computed by an "
            "independent Python implementation (opsflow/kpi.py) straight from data/seed/sales_orders.csv; the "
            "workflow computes them with SQL plus JavaScript. Planted events: online outage 12 Sep, refund spike "
            "15 Sep, large wholesale day 22 Sep, store outage 29 Sep. Dates from 24 Sep are held out.",
            "items": items,
        },
    )


# ------------------------------------------------------------------------------------------------- purchasing

POLICY = {
    "currency": "NZD",
    "auto_approve_max": 500,
    "manager_max": 5000,
    "split_window_days": 14,
    "budget_codes": ["RET-2026", "WHS-2026", "MKT-2026", "OPS-2026", "IT-2026"],
    "approved_suppliers": [
        "Capital Office Supplies Ltd",
        "Pixel Print Studio Ltd",
        "Harbour Freight Logistics Ltd",
        "Ridgeline Camp Supplies Ltd",
        "Kauri Coast Packaging Ltd",
        "CloudDesk Software Ltd",
        "Metro Travel Desk Ltd",
        "Southern Alps Textiles Ltd",
    ],
    "restricted_keywords": [
        "gift card",
        "voucher",
        "alcohol",
        "wine",
        "beer",
        "spirits",
        "cash advance",
        "personal use",
    ],
    "managers": {
        "Retail": "Emma Clarke",
        "Wholesale": "Tom Reed",
        "Marketing": "Hannah Lewis",
        "Operations": "Luke Bennett",
        "IT": "Luke Bennett",
    },
    "director": "Sarah Mitchell",
    "finance": "Simon Porter",
}

HISTORY = [
    ("2026-09-28", "Jess Moana", "Marketing", "Pixel Print Studio Ltd", 420.0),
    ("2026-09-25", "Leo Martin", "IT", "CloudDesk Software Ltd", 300.0),
    ("2026-09-20", "Claire Dawson", "Retail", "Capital Office Supplies Ltd", 120.0),
    ("2026-09-02", "Owen Parata", "Operations", "Ridgeline Camp Supplies Ltd", 450.0),
]

# id, split, requester, department, supplier, amount, budget code, description, date, categories, route
REQUESTS = [
    (
        "P01",
        "dev",
        "Claire Dawson",
        "Retail",
        "Capital Office Supplies Ltd",
        86.50,
        "RET-2026",
        "Receipt printer rolls and pens for the Newmarket store counter.",
        "2026-10-02",
        ["office_and_equipment"],
        "auto_approve",
    ),
    (
        "P02",
        "dev",
        "Jess Moana",
        "Marketing",
        "Pixel Print Studio Ltd",
        2400.00,
        "MKT-2026",
        "A1 posters and window decals for the Wellington store opening on 14 November.",
        "2026-10-02",
        ["marketing"],
        "manager",
    ),
    (
        "P03",
        "dev",
        "Owen Parata",
        "Operations",
        "Harbour Freight Logistics Ltd",
        7800.00,
        "OPS-2026",
        "Top-up of the Q4 freight contract to cover wholesale deliveries before Christmas.",
        "2026-10-02",
        ["packaging_and_freight"],
        "director",
    ),
    (
        "P04",
        "dev",
        "Ruby Chen",
        "Retail",
        "Capital Office Supplies Ltd",
        150.00,
        "",
        "Label printer tape and a stapler for the stockroom.",
        "2026-10-03",
        ["office_and_equipment"],
        "return_to_requester",
    ),
    (
        "P05",
        "dev",
        "Jess Moana",
        "Marketing",
        "Pixel Print Studio Ltd",
        380.00,
        "MKT-2026",
        "Flyers for the spring sleeping bag sale.",
        "2026-10-03",
        ["marketing"],
        "manager",
    ),
    (
        "P06",
        "dev",
        "Ruby Chen",
        "Retail",
        "Metro Travel Desk Ltd",
        460.00,
        "RET-2026",
        "Return flights Auckland to Wellington for two staff to help set up the new store.",
        "2026-10-03",
        ["travel"],
        "auto_approve",
    ),
    (
        "P07",
        "dev",
        "Owen Parata",
        "Operations",
        "Waikato Pallet Co",
        320.00,
        "OPS-2026",
        "20 wooden pallets for the warehouse racking.",
        "2026-10-04",
        ["office_and_equipment", "packaging_and_freight"],
        "manager",
    ),
    (
        "P08",
        "dev",
        "Leo Martin",
        "Wholesale",
        "CloudDesk Software Ltd",
        1200.00,
        "WHS-2026",
        "Annual licence for the stockist inventory sync app.",
        "2026-10-04",
        ["software"],
        "manager",
    ),
    (
        "P09",
        "dev",
        "Claire Dawson",
        "Retail",
        "Capital Office Supplies Ltd",
        450.00,
        "RET-2026",
        "Nine $50 supermarket vouchers to thank store staff for the stocktake weekend.",
        "2026-10-04",
        ["restricted"],
        "finance_review",
    ),
    (
        "P10",
        "dev",
        "Jess Moana",
        "Marketing",
        "Hawke's Bay Cellars Ltd",
        280.00,
        "MKT-2026",
        "A few cases of local pinot noir for the trade evening with our stockists.",
        "2026-10-05",
        ["restricted"],
        "finance_review",
    ),
    (
        "P11",
        "dev",
        "Owen Parata",
        "Operations",
        "Ridgeline Camp Supplies Ltd",
        4950.00,
        "OPS-2026",
        "Restock of 60 self-inflating sleeping mats for summer.",
        "2026-10-05",
        ["stock"],
        "manager",
    ),
    (
        "P12",
        "dev",
        "Leo Martin",
        "IT",
        "CloudDesk Software Ltd",
        39.00,
        "IT-2026",
        "Monthly password-manager seat for a new hire in customer service.",
        "2026-10-05",
        ["software"],
        "auto_approve",
    ),
    (
        "P13",
        "dev",
        "Ruby Chen",
        "Retail",
        "Ridgeline Camp Supplies Ltd",
        12500.00,
        "RET-2026",
        "Summer stock of Kea tents for all four stores.",
        "2026-10-05",
        ["stock"],
        "director",
    ),
    (
        "P14",
        "dev",
        "Hannah Lewis",
        "Marketing",
        "Pixel Print Studio Ltd",
        220.00,
        "MKT-2026",
        "Business cards for four new staff.",
        "2026-10-06",
        ["marketing", "office_and_equipment"],
        "auto_approve",
    ),
    (
        "P15",
        "dev",
        "Ben Walker",
        "Operations",
        "Capital Office Supplies Ltd",
        310.00,
        "OPS-2026",
        "Noise-cancelling headphones that I'd like to keep for myself and use at the gym.",
        "2026-10-06",
        ["restricted"],
        "finance_review",
    ),
    (
        "P16",
        "dev",
        "Tom Reed",
        "Wholesale",
        "Harbour Freight Logistics Ltd",
        640.00,
        "WHS-2026",
        "Express courier for an urgent stockist order to Queenstown.",
        "2026-10-06",
        ["packaging_and_freight"],
        "director",
    ),
    (
        "P17",
        "heldout",
        "Claire Dawson",
        "Retail",
        "Capital Office Supplies Ltd",
        95.00,
        "RET-2026",
        "Till rolls and cleaning supplies.",
        "2026-10-06",
        ["office_and_equipment"],
        "auto_approve",
    ),
    (
        "P18",
        "heldout",
        "Hannah Lewis",
        "Marketing",
        "Pixel Print Studio Ltd",
        5600.00,
        "MKT-2026",
        "2,000 printed copies of the 2027 trade catalogue.",
        "2026-10-06",
        ["marketing"],
        "director",
    ),
    (
        "P19",
        "heldout",
        "Owen Parata",
        "Operations",
        "Ridgeline Camp Supplies Ltd",
        480.00,
        "OPS-2025",
        "Replacement tent pegs and guy ropes for the demo tents.",
        "2026-10-07",
        ["stock", "office_and_equipment"],
        "return_to_requester",
    ),
    (
        "P20",
        "heldout",
        "Tom Reed",
        "Wholesale",
        "Metro Travel Desk Ltd",
        1850.00,
        "WHS-2026",
        "Trade show trip to Christchurch: flights and two nights' hotel for two people.",
        "2026-10-07",
        ["travel"],
        "director",
    ),
    (
        "P21",
        "heldout",
        "Ruby Chen",
        "Retail",
        "Bay Trophy & Engraving Ltd",
        260.00,
        "RET-2026",
        "Engraved hip flasks filled with whisky as prizes for the staff sales competition.",
        "2026-10-07",
        ["restricted"],
        "finance_review",
    ),
    (
        "P22",
        "heldout",
        "Leo Martin",
        "IT",
        "CloudDesk Software Ltd",
        480.00,
        "IT-2026",
        "Three more help-desk app seats for the support team.",
        "2026-10-07",
        ["software"],
        "manager",
    ),
    (
        "P23",
        "heldout",
        "Owen Parata",
        "Operations",
        "Kauri Coast Packaging Ltd",
        2900.00,
        "OPS-2026",
        "Courier bags and boxes for online orders over the Christmas peak.",
        "2026-10-07",
        ["packaging_and_freight"],
        "manager",
    ),
    (
        "P24",
        "heldout",
        "Claire Dawson",
        "Retail",
        "Capital Office Supplies Ltd",
        499.00,
        "RET-2026",
        "Replacement EFTPOS terminal cable and a label printer.",
        "2026-10-07",
        ["office_and_equipment"],
        "auto_approve",
    ),
]


def make_purchasing() -> None:
    dump(SEED / "policy.json", POLICY)
    history = [
        {
            "id": f"PR{i:04d}",
            "date": d,
            "requester": who,
            "department": dept,
            "supplier": sup,
            "amount_nzd": amt,
            "status": "approved",
            "seed": True,
        }
        for i, (d, who, dept, sup, amt) in enumerate(HISTORY, start=1)
    ]
    dump(SEED / "purchase_history.json", history)
    items = [
        {
            "id": rid,
            "split": split,
            "input": {
                "request_id": rid,
                "requester": who,
                "requester_email": who.lower().replace(" ", ".") + "@example.com",
                "department": dept,
                "supplier": sup,
                "amount_nzd": amt,
                "budget_code": code,
                "description": desc,
                "date": day,
            },
            "expected": {"category": cats, "route": route},
        }
        for rid, split, who, dept, sup, amt, code, desc, day, cats, route in REQUESTS
    ]
    dump(
        SAMPLES / "purchase-approval.json",
        {
            "workflow": "purchase-approval",
            "description": "Invented purchase requests. Labels: spending category (one or more acceptable) and the "
            "approval route required by the policy in data/seed/policy.json. Items marked heldout were never used "
            "while tuning prompts or rules.",
            "items": items,
        },
    )


if __name__ == "__main__":
    make_crm()
    make_invoices()
    make_kpi_samples(make_sales())
    make_purchasing()
    print("data written")
