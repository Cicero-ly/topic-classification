#!/bin/sh
echo "===================  Topic classification starting... ======================="
echo ""
cd /usr/src/app
echo "query limit per collection set to: ${PER_COLLECTION_LIMIT}"
python3 topic_classification.py $PER_COLLECTION_LIMIT
echo ""
echo "===================  Topic classification complete. ========================="