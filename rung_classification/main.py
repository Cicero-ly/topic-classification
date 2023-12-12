import os
import time

from pprint import pprint
from typing import List, Tuple

import pymongo


# We're sticking with the HTML parser included in Python's standard library. See https://www.crummy.com/software/BeautifulSoup/bs4/doc/#installing-a-parser
# If we ever have issues with performance, we should consider lxml, although managing this as a dependency
# can be a bit more of a headache than most of our other strictly-python deps.
# (lxml is written in C, and the python package lxml is simply a
# "pythonic binding" of the underlying libxml2 and libxslt.)

from bs4 import BeautifulSoup
from bson.objectid import ObjectId
from langchain.document_loaders import YoutubeLoader

from youtube_transcript_api._errors import (
    NoTranscriptAvailable,
    NoTranscriptFound,
    TranscriptsDisabled,
    TranslationLanguageNotAvailable,
)

# TODO: LATER: fetch topics from db so this is always up-to-date
import sys
sys.path.insert(1, os.path.join(sys.path[0], '..'))
import constants
import shared_utils

from utils import decouple_rung, identify_rung

from data_stores.mongodb import thoughts_db

PYTHON_ENV = os.environ.get("PYTHON_ENV", "development")

claude = shared_utils.ClaudeLLM()

def get_rung_score(content: str, title: str):

  source = f"Title: {title}\nContent: {content}"
  rung, reason = decouple_rung(identify_rung(source, claude))

  return {"level": rung, "reason": reason,}

# TODO: LATER: something more robust down the road...possibly tapping into our existing rules db collection
# Farzad said that "this will need to be greatly expanded, and in short order"
def filter_bad_candidates_for_rungness(
    thought, parsed_content
) -> Tuple[bool, str]:
    
    """
    Determine if thought should undergo topic classification according to simple filter rules.
    If a thought does not pass the filter, it will also be flagged in the DB to ensure
    it isn't considered again for future processing.
    """

    # General ignore patterns:
    if len(parsed_content) < 450:
        reason = "Ignore content if character count < 450"
        return (False, reason)
    
    if "read more" in parsed_content[-250:]:
        reason = "Ignore truncated content"
        return (False, reason)

    # Specific ignore patterns:
    if "marginalrevolution" in thought["url"]:
        reason = "Ignore Tyler Cowen content"
        return (False, reason)
    if "TGIF" in thought["title"] and "thefp" in thought["url"]:
        reason = 'Ignore "The Free Press" TGIF articles'
        return (False, reason)
    if (
        "mail" in thought["title"]
        and ObjectId("6163165d85b48615886b5718") in thought["voicesInContent"]
    ):
        reason = 'Ignore "mailbag" posts by Matthew Yglesias'
        return (False, reason)
    if ObjectId("64505e4c509cac9a8e7e226d") in thought["voicesInContent"]:
        reason = "Ignore content from the voice 'Public'"
        return (False, reason)
    if (
        ObjectId("60cfdfecdbc5ba3af65ce81e") in thought["voicesInContent"]
        or ObjectId("6144af944d89a998bdef2aef") in thought["voicesInContent"]
    ):
        
        reason = "Ignore Jerry Coyne"
        return (False, reason)
    if ObjectId("6302c1f6bce5b9d5af604a27") in thought["voicesInContent"]:
        reason = "Ignore Alex Gangitano"
        return (False, reason)
    if "johndcook" in thought["url"]:
        reason = "Ignore johndcook.com"
        return (False, reason)
    if ObjectId("6195895295d7549fb48c32d9") in thought["voicesInContent"]:
        reason = "Ignore Milan Singh articles"
        return (False, reason)
    if ObjectId("629970b464906c0bea98fbc7") in thought["voicesInContent"]:
        reason = "Ignore David Pakman articles"
        return (False, reason)
    return (True, "")


# TODO: We'll likely have to store transcript in S3 as opposed to directly in DB sooner than later.
def store_transcript(thought_pointer, transcript):
    thought_collection = thought_pointer["collection"]
    thought_id = thought_pointer["_id"]

    update_op = thoughts_db[thought_collection].update_one(
        {"_id": thought_id}, {"$set": {"content_transcript": transcript}}
    )

    return update_op.modified_count

def parse_youtube_transcript(youtube_url: str):
    transcript = ""
    errors = []
    try:
        # Right now, we are fetching fresh transcripts even if a youtube thought
        # already has a transcript in `content_transcript`, since it was alluded to
        # previously that those were quite poor
        loader = YoutubeLoader.from_youtube_url(youtube_url)
        document_list = loader.load()
        if len(document_list) > 0:
            transcript = document_list[0].page_content
    except (
        NoTranscriptFound
        or NoTranscriptAvailable
        or TranscriptsDisabled
        or TranslationLanguageNotAvailable
    ):
        # Handling these exceptions separately, because the error message
        # is egregiously long (contains information about all the languages that
        # are and aren't available)
        transcript_not_found_error = (
            f"Transcript not available for Youtube video at {youtube_url}. "
        )
        errors.append(transcript_not_found_error)
    except Exception as e:
        print(
            f"Misc. error getting transcript for Youtube video at {youtube_url}—see below:"
        )
        print(e)
        errors.append(str(e))
    finally:
        return (transcript, errors)

def collect_thoughts_for_classification(single_collection_find_limit=1000):
    active_thought_collections = os.environ["ACTIVE_THOUGHT_COLLECTIONS"].split(",")
    print("Active thought collections: ", active_thought_collections)
    thoughts_to_classify = []
    thoughts_to_skip = []
    errors = []

    for collection in active_thought_collections:
        pipeline = [
            {
                "$match": {
                    "flags.avoid_rung_classification": {"$ne": True},
                    "llm_rung": {"$exists": False}, # this can be modified
                    "reviewed": True,
                    "valuable": True,
                    "voicesInContent": {"$ne": None},
                    "title": {"$ne": None},
                    "url": {"$ne": None},
                    "$or": [
                        {"content_text": {"$ne": None}},
                        {"content": {"$ne": None}},
                        {"vid": {"$ne": None}},
                    ],
                }
            },
            {
                "$addFields": {
                    "voices_in_content_count": {"$size": "$voicesInContent"},
                    "editing_users_count": {
                        "$cond": {
                            "if": {"$isArray": "$editingUsers"},
                            "then": {"$size": "$editingUsers"},
                            "else": 0,
                        }
                    },
                },
            },
            {
                "$match": {
                    "voices_in_content_count": {"$gt": 0},
                    "editing_users_count": 0,
                }
            },
            {"$sort": {"_id": pymongo.DESCENDING}},
            {"$limit": single_collection_find_limit},
            {
                "$project": {
                    "url": 1,
                    "vid": 1,
                    "title": 1,
                    "content_text": 1,
                    "content": 1,
                    "voicesInContent": 1,
                }
            },
        ]

        thought_cursor = thoughts_db[collection].aggregate(pipeline)
        for thought in thought_cursor:
            parsed_content = ""

            # Criteria for where to get the content, based on the type of thought and what's available
            thought_is_youtube_video = thought.get("vid") != None
            thought_is_article = (
                thought.get("content_text") != None or thought.get("content") != None
            )
            thought_has_full_text = thought.get("content_text") != None
            thought_needs_HTML_parsing = (
                thought.get("content_text") == None and thought.get("content") != None
            )

            if thought_is_youtube_video:
                transcript, fetch_transcript_errors = parse_youtube_transcript(
                    thought["url"]
                )
                store_transcript(
                    {
                        "collection": constants.youtube_thought_collection,
                        "_id": thought["_id"],
                    },
                    transcript,
                )
                parsed_content = transcript
                errors.extend(fetch_transcript_errors)
            elif thought_is_article:
                if thought_has_full_text:
                    parsed_content = thought["content_text"]
                elif thought_needs_HTML_parsing:
                    soup = BeautifulSoup(thought["content"], "html.parser")
                    parsed_content = soup.get_text()
            else:
                continue

            (
                thought_should_be_processed,
                skipped_reason,
            ) = filter_bad_candidates_for_rungness(thought, parsed_content)
            if thought_should_be_processed:
                thoughts_to_classify.append(
                    {
                        "collection": collection,
                        "_id": thought["_id"],
                        "content": parsed_content,
                        "title": thought["title"],
                    }
                )
            else:
                thoughts_to_skip.append(
                    {
                        "collection": collection,
                        "_id": thought["_id"],
                        "reason": skipped_reason,
                    }
                )

    return (
        active_thought_collections,
        thoughts_to_classify,
        thoughts_to_skip,
        errors,
    )


def main(single_collection_find_limit=10000):
    # Setup/init
    job_id = shared_utils.create_job(constants.workflows["rung_classification"]["name"])
    all_untracked_levels = {}
    thoughts_classified: List[ObjectId] = []
    ai_processing_errors = []

    # Collect thoughts
    (
        active_thought_collections,
        thoughts_to_classify,
        thoughts_to_skip,
        data_collection_errors,
    ) = collect_thoughts_for_classification(single_collection_find_limit)

    # Rungness Score
    for thought in thoughts_to_classify:
        try:
            rung_information = get_rung_score(thought["content"], thought["title"])

            rung_class = rung_information['level']
            if rung_class not in constants.rung_classes:
                if all_untracked_levels.get(rung_class) is not None:
                    all_untracked_levels[rung_class] += 1
                else:
                    all_untracked_levels[rung_class] = 1
            
            fields_to_set = { 'llm_rung': {
                "reason": rung_information['reason'],  # This includes both accepted and untracked topics.
                "level": rung_class
            }}

            update_op = thoughts_db[thought["collection"]].update_one(
                {"_id": thought["_id"]},
                {
                    "$set": fields_to_set,
                    "$push": {
                        "llm_processing_metadata.workflows_completed": {
                            "$each": [
                                {
                                    **constants.workflows["rung_classification"],
                                    "last_performed": shared_utils.get_now(),
                                    "job_id": job_id,
                                },
                                
                            ]
                        },
                        "llm_processing_metadata.all_fields_modified": {
                            "$each": list(fields_to_set.keys())
                        },
                    },
                },
            )

            if update_op.modified_count == 1:
                thoughts_classified.append(thought["_id"])

        except Exception as e:
            print(str(e))
            ai_processing_errors.append(str(e))
            print(e)

    for thought in thoughts_to_skip:
        update_op = thoughts_db[thought["collection"]].update_one(
            {"_id": thought["_id"]},
            {"$set": {"flags.avoid_rung_classification": True}},
        )

    # Finish up, log the job
    shared_utils.update_job(
        job_id,
        {
            "status": "complete",
            "last_updated": shared_utils.get_now(),
            "workflows_completed": [
                constants.workflows["rung_classification"]
            ],
            "job_metadata": {
                "collections_queried": active_thought_collections,
                "thoughts_classified_count": len(thoughts_classified),
                "thoughts_skipped": thoughts_to_skip,
                "thoughts_skipped_count": len(thoughts_to_skip),
                "untracked_levels": all_untracked_levels,
                "errors": {
                    "data_collection_errors": data_collection_errors,
                    "ai_processing_errors": ai_processing_errors,
                },
            },
            "test_job": False if PYTHON_ENV == "production" else True,
        },
    )

    return {
        "quantity_thoughts_classified": len(thoughts_classified),
    }


if __name__ == "__main__":
    tic = time.perf_counter()

    if PYTHON_ENV == "production":
        single_collection_find_limit = int(os.environ["SINGLE_COLLECTION_FIND_LIMIT"])
    elif PYTHON_ENV == "data_analysis":
        # A larger `n` for testing AI performance and performing more substantive data analysis.
        single_collection_find_limit = 100
    else:
        # A small `n` for operational testing/container testing.
        single_collection_find_limit = 3
    print(
        "Limit for querying each collection has been set to: ",
        single_collection_find_limit,
    )
    x = main(single_collection_find_limit=single_collection_find_limit)

    toc = time.perf_counter()

    pprint(x)
    print(f"Time elapsed: {toc-tic:0.4f}")
