#!/bin/bash
# Run the AI Washing Detector pipeline overnight
# Usage: ./run_pipeline.sh

cd "$(dirname "$0")/Al Washing Detector"

export AI_WASHER_DATABASE_URL="postgresql+psycopg://hedge:hedge@localhost:5432/ai_hedge_fund"
export AI_WASHER_EDGAR_IDENTITY="AIHedgeFundResearch research@aihedgefund.dev"
export AI_WASHER_LOG_LEVEL="INFO"
export OMP_NUM_THREADS=1
export PYTORCH_ENABLE_MPS_FALLBACK=0
export PYTHONPATH="$(pwd)/src"

echo "Starting AI Washing Detector pipeline at $(date)"
echo "Log: /tmp/ai_washer_pipeline.log"
echo "PID will be logged below"

nohup .venv/bin/python -m ai_washer pipeline run > /tmp/ai_washer_pipeline.log 2>&1 &
PID=$!
echo "Pipeline PID: $PID"
echo "$PID" > /tmp/ai_washer_pipeline.pid

# Wait a moment and check if it's still alive
sleep 10
if ps -p $PID > /dev/null 2>&1; then
    echo "Pipeline is running. Check progress with:"
    echo "  tail -f /tmp/ai_washer_pipeline.log"
    echo "  docker exec ai_hedge_fund_postgres psql -U hedge -d ai_hedge_fund -c 'SELECT COUNT(DISTINCT company_id) FROM daily_scores;'"
else
    echo "Pipeline exited early. Check /tmp/ai_washer_pipeline.log for errors."
    tail -20 /tmp/ai_washer_pipeline.log
fi
