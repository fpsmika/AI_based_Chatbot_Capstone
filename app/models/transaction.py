from sqlalchemy import Column, String, Integer, Date
from sqlalchemy.sql import func
from app.db.base import Base

class Transaction(Base):
    """
    SQLAlchemy model for the transactions table.
    Matches your simplified schema with only these fields:
    TransactionID, FacilityID, FacilityType, Region, BedSize, 
    Month, Year, LoadDate, Vendor
    """
    __tablename__ = "transactions"

    TransactionID = Column(String(50), primary_key=True)
    FacilityID = Column(String(50), nullable=False)
    FacilityType = Column(String(100), nullable=False)
    Region = Column(String(100), nullable=False)
    BedSize = Column(String(50), nullable=False)
    Month = Column(Integer, nullable=False)
    Year = Column(Integer, nullable=False)
    LoadDate = Column(Date, nullable=False)
    Vendor = Column(String(200), nullable=False)

    def __repr__(self):
        return f"<Transaction {self.TransactionID} - {self.Vendor}>"