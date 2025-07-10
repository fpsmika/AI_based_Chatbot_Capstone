import pandas as pd

# Load your dataset
df = pd.read_csv("app/data/generated_fake_supply_data.csv")

# Create Vendor Master Data
vendor_master = df[["Vendor", "VendorID", "Manufacturer", "ManufacturerID"]].drop_duplicates().reset_index(drop=True)

# Create Category Master Data
category_master = df[["ItemDesc", "ManufacturercatalogNum"]].drop_duplicates().reset_index(drop=True)

# Save to CSV
vendor_master.to_csv("app/data/vendor_master_data.csv", index=False)
category_master.to_csv("app/data/category_master_data.csv", index=False)

print("Vendor and Category Master Data have been created successfully.")
