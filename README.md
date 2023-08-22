# Cicero Topic Classification

## Overview

Topic Classification is one of several ML pipelines we perform at Cicero. It's meant to populate a thought's "legacy topics" (to be distinguished from "Wikipedia" topics). Legacy topics are the topics shown to users during onboarding.

Topic classification is performed in two steps:
1. **Summarization** (using Anthropic's Claude, due to its 100k token context window)
2. **Generating topics** based on step 1's generated summary, using ChatGPT 3.5 Turbo

## Running locally (Docker)
### Build the image and run the container
1. `docker build -t cicero_topic_classification .`
2. `docker run --env-file .env cicero_topic_classification` (Get the .env from a teammate)

## Environment variables

- `PYTHON_ENV` {string}: "production", "development", "data_analysis". See main.py's `main()` to see the difference (it's essentially a lever for the size of the input dataset, and can obviously act as a lever for anything else down the road.)
- `SINGLE_COLLECTION_FIND_LIMIT` {int}: a `limit` set on the MongoDB `.find()` query for each thought collection, _in production only_. When `PYTHON_ENV` is set to `development`, `data_analysis`, or anything else, we do not use this value, instead overriding it in the code. 
  - (Note, that if/when we consolidate all thoughts into one collection, which is ideal, this var will change meaning—it will become a _total_ limit for thoughts to query. Right now, the value of this env var is multiplied by the number of collections in  `ACTIVE_THOUGHT_COLLECTIONS` to get the total # of input thoughts.)
- `ACTIVE_THOUGHT_COLLECTIONS` {string}: a comma-separated list of collections from the `cicero_thoughts` DB to query. Note that there are *no spaces between the commas*:
    ```
    ACTIVE_THOUGHT_COLLECTIONS=custom_articles,yt,news,people
    ```
- `ANTHROPIC_API_KEY` {string}: API key for Anthropic.
- `OPENAI_API_KEY` {string}: API key for OpenAI.
- `MONGO_CONNECTION_STRING` {string}: Connection string for the MongoDB cluster.
- `CI` {boolean}: Is this running in an automated environment?

## How this is used

This is a batch job, and runs at some periodic interval on a separate loop from the primary content ingestion ([Cicero-ly/integrations](https://github.com/cicero-ly/integrations)).

It queries for "valuable" and "reviewed" thoughts (that haven't been looked at for topic classification yet), summarizes them, then assigns topics to the thought itself. We also save ancillary artifacts that we get from this process, including `rejected_topics` (topics which don't fit our current criteria, but we might need or want to analyze later) and `content_transcript` for youtube videos. 

There is also an additional rudimentary filter we use to filter out thoughts _after_ they've been fetched from DB, but should not be processed for the purposes of this pipeline (see `thought_should_be_processed()`).

## How this is deployed

It is deployed as a scheduled batch job, running in AWS ECS (Fargate). See the task definitions in the .aws folder. It is scheduled using AWS EventBridge, with a cron schedule target service as ECS itself. The cron targets the ECS task definition (latest), and runs it once a day. See the AWS Management Console for the current schedule selection to see when it runs.