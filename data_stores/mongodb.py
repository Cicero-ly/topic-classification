from pymongo import MongoClient
import os


client = MongoClient(os.environ["MONGO_CONNECTION_STRING"])

thoughts_db = client["cicero_thoughts"]
logs_db = client["cicero_logs"]
jobs_db = client["cicero_jobs"]