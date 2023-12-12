from langchain.llms.base import LLM

from typing import Optional, List, Mapping, Any, Dict
from anthropic import Anthropic, HUMAN_PROMPT, AI_PROMPT
import os

from data_stores.mongodb import jobs_db
import datetime
import bson.objectid

from typing import Dict

ml_jobs = jobs_db["ml_jobs"]

def get_now() -> float:
    return datetime.datetime.now(tz=datetime.timezone.utc).timestamp()

def create_job(job_type):
    assert job_type is not None
    now = get_now()
    insert_op = ml_jobs.insert_one(
        {"type": job_type, "last_updated": now, "status": "started"}
    )
    return insert_op.inserted_id

def get_job(_id: bson.objectid.ObjectId | str) -> Dict:
    job: Dict[str, any] = ml_jobs.find_one({"_id": _id})
    return job


def update_job(_id: bson.objectid.ObjectId | str, document: Dict[str, any]):
    ml_jobs.update_one({"_id": _id}, {"$set": {**document}})
    return

class ClaudeLLM(LLM):

    @property
    def _llm_type(self) -> str:

        return "custom"

    def _call(self, prompt: str, stop: Optional[List[str]] = None) -> str:


        client = Anthropic(
            api_key = os.environ.get("ANTHROPIC_API_KEY"),
        )

        prompt_formatted = (
        f"{HUMAN_PROMPT}{prompt}\n{AI_PROMPT}"
        )

        response = client.completions.create(
        model="claude-instant-v1-100k",
        prompt=prompt_formatted,
        stop_sequences=[HUMAN_PROMPT],
        max_tokens_to_sample=100000,
        temperature=0,
         )

        return response.completion

    @property
    def _identifying_params(self) -> Mapping[str, Any]:
        """Get the identifying parameters."""
        return {

        }
