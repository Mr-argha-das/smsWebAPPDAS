import mongoengine
import certifi
from mongoengine.connection import get_db
from config import settings
import logging

logger = logging.getLogger(__name__)

def connect_db():
    try:
        conn = mongoengine.connect(
            db=settings.DB_NAME,
            host=settings.MONGODB_URL,
            alias="default",
            tlsCAFile=certifi.where(),
            serverSelectionTimeoutMS=10000
        )
        # Verify the server is actually reachable (connect() is lazy)
        conn.admin.command("ping")
        _relax_student_admission_no_index()
        logger.info(f"✅ Connected to MongoDB: {settings.DB_NAME}")
    except Exception as e:
        logger.error(f"❌ MongoDB connection failed: {e}")
        if settings.DEBUG:
            # Dev/demo fallback: in-memory MongoDB (data is NOT persisted)
            try:
                import mongomock
                mongoengine.disconnect(alias="default")
                mongoengine.connect(
                    db=settings.DB_NAME,
                    alias="default",
                    mongo_client_class=mongomock.MongoClient,
                )
                logger.warning("⚠️  Using in-memory mongomock database (DEBUG fallback). Data will be lost on restart!")
                return
            except ImportError:
                logger.error("mongomock not installed; cannot use in-memory fallback")
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
