from fastapi import APIRouter

router = APIRouter()

@router.get("/cosmos/test")
async def test_cosmos():
    return {"message": "Cosmos route is working"}
