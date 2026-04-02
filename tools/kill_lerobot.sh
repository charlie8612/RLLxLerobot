#!/bin/bash
# List all lerobot-teleoperate processes
ps aux | grep '[l]erobot-teleoperate' | awk '{print $2, $8, $11}'
