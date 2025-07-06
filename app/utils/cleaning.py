def validate_and_clean(df):
    """
    Clean and validate data.
    """
    import pandas as pd

    # Drop rows with missing critical columns
    df = df.dropna(subset=[
        "TransactionID" if "TransactionID" in df.columns else "PurchaseID",
        "FacilityID",
        "LoadDate",
        "Quantity",
        "PricePaid",
        "TotalSpend"
    ])

    # Convert dates
    df["LoadDate"] = pd.to_datetime(df["LoadDate"], errors="coerce")

    # Drop invalid dates
    df = df.dropna(subset=["LoadDate"])

    # Remove negatives or zero
    df = df[df["Quantity"] > 0]
    df = df[df["PricePaid"] > 0]

    df = df.reset_index(drop=True)
    return df
