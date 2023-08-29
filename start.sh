#!/bin/sh
set -e
echo "===================  Topic classification starting... ======================="
echo ""
cd /usr/src/app
python3 main.py
echo ""
echo "===================  Topic classification complete. ========================="