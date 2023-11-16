#!/bin/sh
set -e
echo "===================  Topic classification starting... ======================="
echo ""
cd /usr/src/app/topic_classifcation
python3 main.py
echo ""
echo "===================  Topic classification complete. ========================="
set -e
echo "===================  Rung classification starting... ======================="
echo ""
cd /usr/src/app/rung_classification
python3 main.py
echo ""
echo "===================  Rung classification complete. ========================="