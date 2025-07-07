import pandas as pd
import random
from faker import Faker

fake = Faker()

def generate_fake_supply_data(num_records=100000, output_file="app/data/generated_fake_supply_data.csv"):
    records = []

    # Master data for relationships
    facility_types = ["Hospital", "Clinic", "Non Hospital"]
    regions = ["Pacific", "Mountain", "South Atlantic", "Midwest"]
    vendors = [
        {"Vendor": "Cencora", "VendorID": 609547},
        {"Vendor": "Bayer Corp Div Bayer AG", "VendorID": 223180},
        {"Vendor": "McKesson", "VendorID": 778899},
    ]

    for _ in range(num_records):
        vendor = random.choice(vendors)
        record = {
            "TransactionID": fake.unique.random_int(min=2000000000, max=3000000000),
            "FacilityID": random.randint(1000, 9999),
            "FacilityType": random.choice(facility_types),
            "Region": random.choice(regions),
            "BedSize": random.choice(["0-0", "1-50", "51-200"]),
            "Month": random.randint(1, 12),
            "Year": random.choice([2022, 2023, 2024]),
            "LoadDate": fake.date_between(start_date="-2y", end_date="today"),
            "Vendor": vendor["Vendor"],
            "VendorID": vendor["VendorID"],
            "Manufacturer": vendor["Vendor"],
            "ManufacturerID": vendor["VendorID"],
            "ManufacturercatalogNum": fake.bothify(text="????-#####"),
            "ItemDesc": fake.catch_phrase(),
            "Quantity": random.randint(1, 20),
            "PricePaid": round(random.uniform(5, 500), 2),
        }
        record["TotalSpend"] = round(record["Quantity"] * record["PricePaid"], 2)
        records.append(record)

    df = pd.DataFrame(records)
    df.to_csv(output_file, index=False)
    print(f" Generated {num_records} supply records in {output_file}")

# Run directly
if __name__ == "__main__":
    generate_fake_supply_data()
