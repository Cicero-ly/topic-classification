#!/bin/sh
echo "===================  Topic classification starting... ======================="
echo ""
cd /usr/src/app
python3 topic_classification.py $PER_COLLECTION_LIMIT
echo ""
echo "===================  Topic classification complete. ========================="