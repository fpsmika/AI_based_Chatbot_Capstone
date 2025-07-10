import pandas as pd
import random
from faker import Faker

fake = Faker()

def generate_fake_purchase_data(num_records=1000000, output_file="app/data/generated_fake_purchase_data.csv"):
    records = []

   
    item_descriptions = [
        "Aspirin 500mg Tablets",
        "Surgical Gloves",
        "IV Drip Set",
        "Thermometer",
        "Syringe 10ml"
    ]
    vendors = [
        {"Vendor": "Cencora", "VendorID": 609547},
        {"Vendor": "Bayer Corp Div Bayer AG", "VendorID": 223180},
        {"Vendor": "McKesson", "VendorID": 778899},
    ]

    for _ in range(num_records):
        vendor = random.choice(vendors)
        quantity = random.randint(1, 50)
        price_paid = round(random.uniform(1, 200), 2)
        record = {
            "PurchaseID": fake.unique.random_int(min=3000000000, max=4000000000),
            "PurchaseDate": fake.date_between(start_date="-2y", end_date="today"),
            "Vendor": vendor["Vendor"],
            "VendorID": vendor["VendorID"],
            "ItemDesc": random.choice(item_descriptions),
            "Quantity": quantity,
            "UnitPrice": price_paid,
        }
        record["TotalCost"] = round(quantity * price_paid, 2)
        records.append(record)

    df = pd.DataFrame(records)
    df.to_csv(output_file, index=False)
    print(f"Generated {num_records} purchase records in {output_file}")

# Run directly
if __name__ == "__main__":
    generate_fake_purchase_data()
