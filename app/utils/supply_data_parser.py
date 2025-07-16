import pandas as pd
from typing import List, Dict

MONTHS = {
    1: "January", 2: "February", 3: "March", 4: "April",
    5: "May", 6: "June", 7: "July", 8: "August",
    9: "September", 10: "October", 11: "November", 12: "December"
}

def csv_to_purchase_chunks(df: pd.DataFrame) -> List[Dict]:
    chunks = []

    for _, row in df.iterrows():
        
        month = MONTHS.get(int(row['Month']), f"Month-{row['Month']}")
        year = int(row['Year'])

        text = (
            f"In {month} {year}, a {row['FacilityType']} facility in the {row['Region']} region "
            f"purchased {row['Quantity']} unit(s) of {row['ItemDesc']} from {row['Vendor']} "
            f"for ${row['TotalSpend']:.2f}."
        )

        metadata = {
            "transaction_id": row.get("TransactionID"),
            "facility_id": row.get("FacilityID"),
            "facility_type": row.get("FacilityType"),
            "region": row.get("Region"),
            "month": row.get("Month"),
            "year": row.get("Year"),
            "vendor": row.get("Vendor"),
            "vendor_id": row.get("VendorID"),
            "manufacturer": row.get("Manufacturer"),
            "item_desc": row.get("ItemDesc"),
            "quantity": row.get("Quantity"),
            "price_paid": row.get("PricePaid"),
            "total_spend": row.get("TotalSpend"),
        }

        chunks.append({
            "text": text,
            "metadata": metadata
        })

    return chunks
