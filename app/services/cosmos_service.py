import os
import logging
from azure.cosmos import CosmosClient, PartitionKey
from azure.cosmos.exceptions import CosmosHttpResponseError
from app.core.config import settings

# Configure logging
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)
handler = logging.StreamHandler()
formatter = logging.Formatter("[%(asctime)s] %(levelname)s] %(message)s")
handler.setFormatter(formatter)
logger.addHandler(handler)

# Read configuration from settings or environment
ENDPOINT       = settings.COSMOS_DB_ENDPOINT
KEY            = settings.COSMOS_DB_KEY
DATABASE_NAME  = settings.COSMOS_DB_DATABASE
CONTAINER_NAME = getattr(settings, 'COSMOS_DB_CONTAINER', 'supply_records')

# Initialize Cosmos client and database
client   = CosmosClient(ENDPOINT, credential=KEY)
database = client.get_database_client(DATABASE_NAME)

# Ensure container exists (idempotent)
try:
    container = database.create_container_if_not_exists(
        id=CONTAINER_NAME,
        partition_key=PartitionKey(path="/id"),
        offer_throughput=settings.COSMOS_DB_THROUGHPUT if hasattr(settings, 'COSMOS_DB_THROUGHPUT') else None
    )
    logger.info(f"Connected to Cosmos container '{CONTAINER_NAME}' in database '{DATABASE_NAME}'")
except CosmosHttpResponseError as e:
    logger.error(f"Error creating/getting container '{CONTAINER_NAME}': {e}")
    raise


def get_cosmos_service():
    """
    Returns:
        azure.cosmos.ContainerProxy: Cosmos DB container client for CRUD operations.
    """
    return container
