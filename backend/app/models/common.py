from datetime import datetime
from uuid import uuid4


def uuid_hex() -> str:
    return uuid4().hex


def data_collection_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")
