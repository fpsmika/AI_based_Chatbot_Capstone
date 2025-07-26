# app/utils/supply_data_parser.py

import pandas as pd
from typing import List, Dict

MONTHS = {
    1: "January",    2: "February", 3: "March",     4: "April",
    5: "May",        6: "June",     7: "July",      8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

def csv_to_purchase_chunks(df: pd.DataFrame) -> List[Dict]:
    def getcol(row: pd.Series, name: str):
        # try exact, then lowercase
        if name in row:
            return row[name]
        return row.get(name.lower())

    chunks: List[Dict] = []

    for _, row in df.iterrows():
        # month/year may come in as int or str
        raw_month = getcol(row, "Month")
        raw_year  = getcol(row, "Year")
        try:
            m = int(raw_month)
        except:
            m = None
        try:
            y = int(raw_year)
        except:
            y = None

        month_name = MONTHS.get(m, f"Month-{m}") if m else "Unknown month"
        year_name  = str(y) if y else "Unknown year"

        text = (
            f"In {month_name} {year_name}, a {getcol(row,'FacilityType')} facility in the "
            f"{getcol(row,'Region')} region purchased {getcol(row,'Quantity')} unit(s) of "
            f"{getcol(row,'ItemDesc')} from {getcol(row,'Vendor')} for "
            f"${float(getcol(row,'TotalSpend') or 0):.2f}."
        )

        metadata = {
            "id":               getcol(row, "id"),            # carry through your UUID
            "transaction_id":   getcol(row, "TransactionID"),
            "facility_id":      getcol(row, "FacilityID"),
            "facility_type":    getcol(row, "FacilityType"),
            "region":           getcol(row, "Region"),
            "month":            m,
            "year":             y,
            "vendor":           getcol(row, "Vendor"),
            "vendor_id":        getcol(row, "VendorID"),
            "manufacturer":     getcol(row, "Manufacturer"),
            "item_desc":        getcol(row, "ItemDesc"),
            "quantity":         getcol(row, "Quantity"),
            "price_paid":       getcol(row, "PricePaid"),
            "total_spend":      getcol(row, "TotalSpend"),
        }

        chunks.append({
            "text":     text,
            "metadata": metadata
        })

    return chunks
