from azure.cosmos import CosmosClient, PartitionKey
from app.core.config import settings

# Initialize the Cosmos client
client = CosmosClient(
    url=settings.COSMOS_DB_ENDPOINT,
    credential=settings.COSMOS_DB_KEY
)

# Reference the database
database = client.create_database_if_not_exists(id=settings.COSMOS_DB_DATABASE)

# Create or get the container
container = database.create_container_if_not_exists(
    id="supply_records",
    partition_key=PartitionKey(path="/id")
)

def get_cosmos_service():
    """
    Returns the Cosmos DB container for CRUD operations.
    """
    return container
