#!/bin/bash
# Continuous scanner until 10 valid keys found

TARGET_VALID_KEYS=10
CHECK_INTERVAL=120  # Check every 2 minutes

echo "=== Starting continuous scan until 10 valid keys ==="
echo "Target: $TARGET_VALID_KEYS valid keys"
echo "Check interval: ${CHECK_INTERVAL}s"
echo "Started: $(date)"
echo ""

while true; do
    # Check current valid key count
    VALID_COUNT=$(python -c "
import sqlite3
conn = sqlite3.connect('leaked_keys.db')
cur = conn.cursor()
cur.execute('SELECT COUNT(*) FROM leaked_keys WHERE status=\"valid\"')
count = cur.fetchone()[0]
print(count)
conn.close()
" 2>/dev/null || echo "0")

    echo "[$(date +%H:%M:%S)] Valid keys: $VALID_COUNT / $TARGET_VALID_KEYS"

    # Check if target reached
    if [ "$VALID_COUNT" -ge "$TARGET_VALID_KEYS" ]; then
        echo ""
        echo "=== TARGET REACHED ==="
        echo "Found $VALID_COUNT valid keys!"
        echo "Exporting results..."
        python main.py --export valid_keys_final.txt --status valid
        echo "Results saved to: valid_keys_final.txt"
        exit 0
    fi

    # Continue scanning
    echo "Scanning... (Press Ctrl+C to stop)"
    timeout 60 python main.py --all-sources 2>&1 | grep -E "Found|发现|valid|VALID" || true

    sleep $CHECK_INTERVAL
done
