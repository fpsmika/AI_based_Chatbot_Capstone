import pandas as pd
import numpy as np
from typing import List, Any

def ingest_file(file_path: str, chunksize: int = 10000) -> pd.DataFrame:
    if file_path.endswith(".csv"):
        chunks = []
        for chunk in pd.read_csv(file_path, chunksize=chunksize):
            chunks.append(chunk)
        df = pd.concat(chunks, ignore_index=True)
    elif file_path.endswith((".xls", ".xlsx")):
        df = pd.read_excel(file_path)
    else:
        raise ValueError("Unsupported file type. Only .csv, .xls, .xlsx are allowed.")
    
    # Replace ±∞ with NaN, then convert all NaN to None for JSON serialization
    df.replace([np.inf, -np.inf], np.nan, inplace=True)
    df = df.where(df.notnull(), None)

    return df

def load_dataframe_from_json(headers: List[str], rows: List[List[Any]]) -> pd.DataFrame:
    if not headers or not rows:
        raise ValueError("Headers and rows must not be empty.")

    df = pd.DataFrame(rows, columns=headers)
    return df
