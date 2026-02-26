#!/bin/bash
# Serve all websites on fixed ports
# GSM: 1313, JM: 1314, Daily-Agile: 1315, Stoicagile: 1316

echo "Stopping any existing Hugo servers..."
pkill -f "hugo server" 2>/dev/null || true
sleep 1

echo ""
echo "Starting all sites..."
echo "================================"

# GSM on port 1313
cd /Users/johnmcfadyen/projects/websites/growingscrummasters.com
hugo server --port 1313 --disableFastRender &
echo "✓ growingscrummasters.com → http://localhost:1313"

# JM on port 1314
cd /Users/johnmcfadyen/projects/websites/johnmcfadyen.com
hugo server --port 1314 --disableFastRender &
echo "✓ johnmcfadyen.com → http://localhost:1314"

# Daily-Agile on port 1315
cd /Users/johnmcfadyen/projects/websites/daily-agile.com
hugo server --port 1315 --disableFastRender &
echo "✓ daily-agile.com → http://localhost:1315"

# Stoicagile on port 1316
cd /Users/johnmcfadyen/projects/websites/unleashingthepowerofstoicagile.com
hugo server --port 1316 --disableFastRender &
echo "✓ unleashingthepowerofstoicagile.com → http://localhost:1316"

echo ""
echo "================================"
echo "All sites running. Press Ctrl+C to stop all."
echo ""

# Wait for any process to exit
wait
