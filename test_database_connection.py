"""
Run this script to diagnose database connection issues
"""
import os
import sys
import pyodbc
from pathlib import Path

# Add the project root to the Python path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from app.core.config import settings
from app.core.config import test_database_connection

def main():
    print("🔍 Database Connection Diagnostic Tool")
    print("=" * 50)
    
    # 1. Check environment variables
    print("\n1. Environment Variables Check:")
    env_vars = [
        'SQL_SERVER', 'SQL_DATABASE', 'SQL_USERNAME', 'SQL_PASSWORD',
        'DATABASE_URL', 'DATABASE_SERVER', 'DATABASE_NAME', 
        'DATABASE_USERNAME', 'DATABASE_PASSWORD'
    ]
    
    for var in env_vars:
        value = getattr(settings, var, None) or os.getenv(var, "")
        if value:
            if 'PASSWORD' in var:
                print(f"  ✅ {var}: {'*' * len(value)}")
            else:
                print(f"  ✅ {var}: {value}")
        else:
            print(f"  ❌ {var}: Not set")
    
    # 2. Check configuration status
    print("\n2. Configuration Status:")
    try:
        db_status = settings.get_database_config_status()
        for key, value in db_status.items():
            icon = "✅" if value else "❌"
            print(f"  {icon} {key}: {value}")
    except AttributeError:
        print("  ⚠️  get_database_config_status() method not available in settings")
        print("  ℹ️  Basic configuration check:")
        print(f"  ✅ SQL_SERVER: {bool(settings.SQL_SERVER)}")
        print(f"  ✅ SQL_DATABASE: {bool(settings.SQL_DATABASE)}")
        print(f"  ✅ SQL_USERNAME: {bool(settings.SQL_USERNAME)}")
        print(f"  ✅ SQL_PASSWORD: {'*' * len(settings.SQL_PASSWORD) if settings.SQL_PASSWORD else False}")
        print(f"  ✅ SQL_DRIVER: {bool(settings.SQL_DRIVER)}")
    
    # 3. Generated connection strings (masked for security)
    print("\n3. Generated Connection Strings:")
    try:
        sqlalchemy_url = settings.get_database_url
        if sqlalchemy_url:
            # Mask password in URL for display
            masked_url = sqlalchemy_url
            if ':' in masked_url and '@' in masked_url:
                parts = masked_url.split('://')
                if len(parts) == 2:
                    protocol = parts[0]
                    rest = parts[1]
                    if '@' in rest:
                        credentials, server_db = rest.split('@', 1)
                        if ':' in credentials:
                            username, password = credentials.split(':', 1)
                            masked_url = f"{protocol}://{username}:{'*' * len(password)}@{server_db}"
            print(f"  SQLAlchemy URL: {masked_url}")
        else:
            print(f"  ❌ SQLAlchemy URL: Not generated")
    except AttributeError:
        print("  ⚠️  get_database_url property not available in settings")
    
    try:
        raw_conn_string = settings.get_raw_connection_string()
        if raw_conn_string:
            # Mask password in connection string
            masked_conn = raw_conn_string
            if 'PWD=' in masked_conn:
                import re
                masked_conn = re.sub(r'PWD=[^;]+;', 'PWD=***;', masked_conn)
            print(f"  Raw Connection: {masked_conn}")
        else:
            print(f"  ❌ Raw Connection String: Not generated")
    except AttributeError:
        print("  ⚠️  get_raw_connection_string() method not available in settings")
    
    # 4. Test actual connection
    print("\n4. Testing Database Connection:")
    result = test_database_connection()
    
    if result["success"]:
        print(f"  ✅ Connection successful!")
        print(f"  📋 Server version: {result['server_version']}")
    else:
        print(f"  ❌ Connection failed!")
        print(f"  🚨 Error: {result['error']}")
        print(f"  🔧 Error type: {result['error_type']}")
        if result.get('guidance'):
            print(f"  💡 Guidance: {result['guidance']}")
    
    # 5. Network connectivity test
    print("\n5. Network Connectivity Test:")
    if settings.SQL_SERVER:
        server = settings.SQL_SERVER
        if not server.endswith('.database.windows.net'):
            server = f"{server}.database.windows.net"
        
        try:
            import socket
            sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            sock.settimeout(10)
            result = sock.connect_ex((server, 1433))
            sock.close()
            
            if result == 0:
                print(f"  ✅ Can reach {server}:1433")
            else:
                print(f"  ❌ Cannot reach {server}:1433 (error code: {result})")
        except Exception as e:
            print(f"  ❌ Network test failed: {e}")
    else:
        print("  ⚠️  No server configured to test")
    
    # 6. ODBC Driver check
    print("\n6. ODBC Driver Check:")
    try:
        drivers = pyodbc.drivers()
        target_driver = settings.SQL_DRIVER if hasattr(settings, 'SQL_DRIVER') else 'ODBC Driver 18 for SQL Server'
        if target_driver in drivers:
            print(f"  ✅ {target_driver} is available")
        else:
            print(f"  ❌ {target_driver} is NOT available")
            print(f"  📋 Available drivers: {', '.join(drivers)}")
    except Exception as e:
        print(f"  ❌ Error checking drivers: {e}")
    
    # 7. Recommendations
    print("\n7. Recommendations:")
    if not result["success"]:
        print("  🔧 To fix connection issues:")
        print("     1. Ensure your Azure SQL Database is running (not paused)")
        print("     2. Check firewall rules in Azure portal")
        print("     3. Verify credentials are correct")
        print("     4. Try connecting with Azure Data Studio or SSMS")
        print("     5. Check if database exists and is accessible")
        
        if "database" in result.get("error", "").lower() and "not currently available" in result.get("error", "").lower():
            print("\n  🚨 DATABASE APPEARS TO BE PAUSED!")
            print("     Run this Azure CLI command to resume:")
            print(f"     az sql db resume --name {settings.SQL_DATABASE} --server {settings.SQL_SERVER.replace('.database.windows.net', '')} --resource-group <your-resource-group>")
    
    print("\n" + "=" * 50)
    print("🏁 Diagnostic complete!")

if __name__ == "__main__":
    main()