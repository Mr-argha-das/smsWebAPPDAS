import mongoengine
from config import settings
import logging

logger = logging.getLogger(__name__)

def connect_db():
    try:
        mongoengine.connect(
            db=settings.DB_NAME,
            host=settings.MONGODB_URL,
            alias="default"
        )
        logger.info(f"✅ Connected to MongoDB: {settings.DB_NAME}")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        raise e

def disconnect_db():
    mongoengine.disconnect()
    logger.info("Disconnected from MongoDB")
