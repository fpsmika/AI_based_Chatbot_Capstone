import pandas as pd
import logging

logger = logging.getLogger(__name__)

def transform_data(df: pd.DataFrame) -> pd.DataFrame:
    """
    Clean and transform purchase data:
    - Handle both PascalCase and normalized column names
    - Rename to canonical fields for SQL database
    - Cast data types safely
    - Derive UnitCost
    - Preserve original values
    """
    
    # Log original columns to debug
    logger.info(f"Original columns: {list(df.columns)}")
    
    # Create a copy to avoid modifying original
    df = df.copy()
    
    # FIXED: Handle the actual column names from your CSV data
    # Map both original PascalCase AND normalized names to canonical schema
    column_mapping = {
        # Original PascalCase names from your CSV
        "TransactionID": "TransactionID",
        "FacilityID": "FacilityID", 
        "FacilityType": "FacilityType",
        "Region": "Region",
        "BedSize": "BedSize",
        "Month": "Month",
        "Year": "Year",
        "LoadDate": "LoadDate",
        "Vendor": "Vendor",
        "VendorID": "VendorID",
        "Manufacturer": "Manufacturer",
        "ManufacturerID": "ManufacturerID",
        "ManufacturercatalogNum": "ManufacturercatalogNum",
        "ItemDesc": "ItemDesc",
        "Quantity": "Quantity",
        "PricePaid": "PricePaid",
        "TotalSpend": "TotalSpend",
        
        # Also handle normalized lowercase versions (in case they exist)
        "transactionid": "TransactionID",
        "facilityid": "FacilityID",
        "facilitytype": "FacilityType", 
        "region": "Region",
        "bedsize": "BedSize",
        "month": "Month",
        "year": "Year",
        "loaddate": "LoadDate",
        "vendor": "Vendor",
        "vendorid": "VendorID",
        "manufacturer": "Manufacturer",
        "manufacturerid": "ManufacturerID",
        "manufacturercatalognumber": "ManufacturercatalogNum",
        "manufacturercatalognum": "ManufacturercatalogNum",
        "itemdesc": "ItemDesc",
        "quantity": "Quantity",
        "pricepaid": "PricePaid",
        "totalspend": "TotalSpend",
        
        # Handle variations in column names
        "transaction_id": "TransactionID",
        "facility_id": "FacilityID",
        "facility_type": "FacilityType",
        "bed_size": "BedSize",
        "load_date": "LoadDate",
        "vendor_id": "VendorID",
        "manufacturer_id": "ManufacturerID",
        "catalog_num": "ManufacturercatalogNum",
        "item_desc": "ItemDesc",
        "price_paid": "PricePaid",
        "total_spend": "TotalSpend"
    }
    
    # Apply column mapping only for columns that exist
    rename_dict = {}
    for old_name, new_name in column_mapping.items():
        if old_name in df.columns:
            rename_dict[old_name] = new_name
    
    if rename_dict:
        df = df.rename(columns=rename_dict)
        logger.info(f"Renamed columns: {rename_dict}")
    
    # Log final columns after renaming
    logger.info(f"Final columns: {list(df.columns)}")
    
    # FIXED: Safe type casting with error handling
    try:
        # Handle numeric fields safely
        if 'FacilityID' in df.columns:
            df["FacilityID"] = pd.to_numeric(df["FacilityID"], errors='coerce').fillna(0).astype(int)
        
        if 'Month' in df.columns:
            df["Month"] = pd.to_numeric(df["Month"], errors='coerce').fillna(1).astype(int)
            
        if 'Year' in df.columns:
            df["Year"] = pd.to_numeric(df["Year"], errors='coerce').fillna(2022).astype(int)
            
        if 'Quantity' in df.columns:
            df["Quantity"] = pd.to_numeric(df["Quantity"], errors='coerce').fillna(0).astype(int)
            
        if 'PricePaid' in df.columns:
            df["PricePaid"] = pd.to_numeric(df["PricePaid"], errors='coerce').fillna(0.0).astype(float)
            
        if 'TotalSpend' in df.columns:
            df["TotalSpend"] = pd.to_numeric(df["TotalSpend"], errors='coerce').fillna(0.0).astype(float)
        
        # Handle date field safely
        if 'LoadDate' in df.columns:
            try:
                df["LoadDate"] = pd.to_datetime(df["LoadDate"], errors='coerce')
                # Convert to ISO date string format for SQL
                df["LoadDate"] = df["LoadDate"].dt.strftime('%Y-%m-%d')
            except Exception as date_error:
                logger.warning(f"Date parsing error: {date_error}")
                # Fallback to string representation
                df["LoadDate"] = df["LoadDate"].astype(str)
        
        # Derived column (unit cost)
        if 'TotalSpend' in df.columns and 'Quantity' in df.columns:
            # Avoid division by zero
            df["UnitCost"] = df["TotalSpend"] / df["Quantity"].replace(0, 1)
        
        # Clean string fields - preserve original values, just trim whitespace
        string_fields = ['TransactionID', 'FacilityType', 'Region', 'BedSize', 'Vendor', 'VendorID', 
                        'Manufacturer', 'ManufacturerID', 'ManufacturercatalogNum', 'ItemDesc']
        
        for field in string_fields:
            if field in df.columns:
                df[field] = df[field].astype(str).str.strip()
                # Don't force to uppercase - preserve original case
        
        logger.info("Data transformation completed successfully")
        
        # Log sample of transformed data
        if len(df) > 0:
            sample_row = df.iloc[0].to_dict()
            logger.info(f"Sample transformed row: {sample_row}")
        
    except Exception as e:
        logger.error(f"Error during data transformation: {e}")
        raise
    
    return df
