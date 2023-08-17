#!/bin/sh
echo "===================  Topic classification starting... ======================="
echo ""
cd /usr/src/app
# local testing only:
# . .venv/bin/activate
python3 main.py
echo ""
echo "===================  Topic classification complete. ========================="