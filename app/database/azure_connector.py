import pyodbc
from app.core.config import settings

class AzureSQLConnector:
    @staticmethod
    def get_connection():
        conn_str = (
            f"Driver={{{settings.SQL_DRIVER}}};"
            f"Server=tcp:{settings.SQL_SERVER},1433;"
            f"Database={settings.SQL_DATABASE};"
            f"Uid={settings.SQL_USERNAME};"
            f"Pwd={settings.SQL_PASSWORD};"
            f"Encrypt=yes;"
            f"TrustServerCertificate=no;"
        )
        return pyodbc.connect(conn_str)