#!/bin/sh
#
set -e
cd /usr/src/app

echo "===================  Topic classification starting... ======================="
echo ""
python3 topic_classification/main.py
echo ""
echo "===================  Topic classification complete. ========================="

echo "===================  Rung classification starting... ======================="
echo ""
python3 rung_classification/main.py
echo ""
echo "===================  Rung classification complete. ========================="
