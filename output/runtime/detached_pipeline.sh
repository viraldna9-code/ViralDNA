#!/bin/bash
# Detached pipeline launcher - survives parent death
cd /home/jay/ViralDNA
exec /usr/bin/python3 -u run_local.py --mode normal > output/runtime/pipeline_live.log 2>&1
