import pandas as pd


def transform_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and transform purchase data:
    - Normalize column names
    - Rename to canonical fields
    - Cast data types
    - Derive UnitCost
    - Uppercase FacilityType
    """
    # a) Normalize column names
    df.columns = (
        df.columns.str.strip()
                  .str.replace(r"\s+", "_", regex=True)
                  .str.replace(r"[^0-9a-zA-Z_]", "", regex=True)
                  .str.lower()
    )

    # b) Rename fields to canonical schema
    df = df.rename(columns={
        "transactionid": "transaction_id",
        "facilityid": "facility_id",
        "facilitytype": "facility_type",
        "region": "region",
        "bedsize": "bed_size",
        "month": "month",
        "year": "year",
        "loaddate": "load_date",
        "vendor": "vendor",
        "vendorid": "vendor_id",
        "manufacturer": "manufacturer",
        "manufacturerid": "manufacturer_id",
        "manufacturercatalognumber": "catalog_num",
        "itemdesc": "item_desc",
        "quantity": "quantity",
        "pricepaid": "price_paid",
        "totalspend": "total_spend",
    })

    # c) Cast types
    df["facility_id"] = df["facility_id"].astype(int)
    df["month"] = df["month"].astype(int)
    df["year"] = df["year"].astype(int)
    df["quantity"] = df["quantity"].astype(int)
    df["price_paid"] = df["price_paid"].astype(float)
    df["total_spend"] = df["total_spend"].astype(float)
    df["load_date"] = pd.to_datetime(df["load_date"]).dt.date.astype(str)

    # d) Derived column
    df["unit_cost"] = df["total_spend"] / df["quantity"]

    # e) Standardize facility type formatting
    df["facility_type"] = df["facility_type"].str.upper()

    return df
