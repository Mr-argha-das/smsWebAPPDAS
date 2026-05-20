import mongoengine
from mongoengine.connection import get_db
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
        _relax_student_admission_no_index()
        logger.info(f"✅ Connected to MongoDB: {settings.DB_NAME}")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        raise e


def _relax_student_admission_no_index():
    collection = get_db(alias="default")["students"]
    for name, spec in collection.index_information().items():
        keys = spec.get("key", [])
        if spec.get("unique") and keys == [("admission_no", 1)]:
            collection.drop_index(name)
            logger.info("Dropped global unique admission_no index; admission numbers are now checked in application scope")

def disconnect_db():
    mongoengine.disconnect()
    logger.info("Disconnected from MongoDB")
