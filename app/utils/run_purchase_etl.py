from .pipeline import ingest_large_csv
from .cleaning import validate_and_clean
from .transform import transform_data

DATA_PATH = "app/data/raw_purchase_data.csv"

df = ingest_large_csv(DATA_PATH)

print("Purchase ingestion complete.")

df_clean = validate_and_clean(df)
print("Purchase cleaning complete.")

df_transformed = transform_data(df_clean)
print("Purchase transformation complete.")

df_transformed.to_csv("app/data/cleaned_purchase_data.csv", index=False)
print("Purchase ETL completed. Cleaned file saved.")
