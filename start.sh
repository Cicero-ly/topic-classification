#!/bin/sh
set -e
echo "===================  Topic classification starting... ======================="
echo ""
cd /usr/src/app
python3 topic_classification/main.py
echo ""
echo "===================  Topic classification complete. ========================="
set -e
echo "===================  Rung classification starting... ======================="
echo ""
python3 rung_classification/main.py
echo ""
echo "===================  Rung classification complete. ========================="