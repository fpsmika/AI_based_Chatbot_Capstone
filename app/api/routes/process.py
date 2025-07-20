from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Any
from app.utils.pipeline import load_dataframe_from_json

router = APIRouter()

class ParsedFileData(BaseModel):
    headers: List[str]
    rows: List[List[Any]]

@router.post("/process")
async def process_parsed_data(data: ParsedFileData):
    try:
        df = load_dataframe_from_json(data.headers, data.rows)

       
        print("✅ Received DataFrame:")
        print(df.head())

        return {
            "status": "success",
            "columns": df.columns.tolist(),
            "rows_loaded": len(df)
        }
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
