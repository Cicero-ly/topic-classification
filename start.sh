echo "===================  Topic classification starting... ======================="
echo ""
cd /usr/src/app
# local only:
# . .venv/bin/activate
python3 topic_classification.py $PER_COLLECTION_LIMIT
echo ""
echo "===================  Topic classification complete. ========================="