def transform_data(df):
    """
    Create computed columns.
    """
    df["UnitCost"] = df["TotalSpend"] / df["Quantity"]
    df["FacilityType"] = df["FacilityType"].str.upper()
    return df
