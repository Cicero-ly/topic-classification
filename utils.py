from data_stores.mongodb import jobs_db
import datetime
import bson.objectid
from typing import Dict

ml_jobs = jobs_db["ml_jobs"]


def get_now() -> float:
    return datetime.datetime.now(tz=datetime.timezone.utc).timestamp()


def create_job():
    now = get_now()
    insert_op = ml_jobs.insert_one(
        {"type": "topic_classification", "last_updated": now, "status": "started"}
    )
    return insert_op.inserted_id


def get_job(_id: bson.objectid.ObjectId | str) -> Dict:
    job: Dict[str, any] = ml_jobs.find_one({"_id": _id})
    return job


def update_job(_id: bson.objectid.ObjectId | str, document: Dict[str, any]):
    ml_jobs.update_one({"_id": _id}, {"$set": {**document}})
    return
