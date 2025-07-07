from database.azure_connector import AzureSQLConnector
from services.llama_service import LlamaService

class TransactionAnalyzer:
    @staticmethod
    def get_transactions_table(limit: int = 50) -> str:
        conn = AzureSQLConnector.get_connection()
        cursor = conn.cursor()
        
        cursor.execute(f"""
            SELECT TOP {limit} 
                TransactionID, FacilityType, Region, 
                Vendor, Year, Month, LoadDate
            FROM transactions
            ORDER BY LoadDate DESC
        """)
        
        # Format as Markdown table
        headers = [column[0] for column in cursor.description]
        rows = cursor.fetchall()
        conn.close()
        
        table = "| " + " | ".join(headers) + " |\n"
        table += "|" + "|".join(["---"] * len(headers)) + "|\n"
        table += "\n".join("| " + " | ".join(str(x) for x in row) + " |" for row in rows)
        return table

    @staticmethod
    def analyze() -> str:
        data = TransactionAnalyzer.get_transactions_table()
        prompt = f"""Analyze these healthcare transactions:
{data}

Provide insights on:
1. Vendor distribution patterns
2. Regional facility trends
3. Data anomalies"""
        
        return LlamaService.query(prompt)