#!/bin/bash
# monitor_progress.sh - Real-time progress monitoring for episode ingestion

echo "🔍 Monitoring Graphiti Episode Ingestion Progress..."
echo "Press Ctrl+C to stop monitoring"
echo ""

# Function to extract progress from logs
get_progress() {
    docker logs pd-graphiti-service --since 1m 2>/dev/null | \
    grep -E "Processing episode [0-9]+/[0-9]+" | \
    tail -1
}

# Function to get API call rate
get_api_rate() {
    local calls=$(docker logs pd-graphiti-service --since 1m 2>/dev/null | \
                 grep -c "x-ratelimit-remaining-requests")
    echo "$calls"
}

# Function to check if still processing
is_processing() {
    local recent_activity=$(docker logs pd-graphiti-service --since 2m 2>/dev/null | \
                          grep -c "HTTP Request: POST https://api.openai.com")
    [[ $recent_activity -gt 0 ]]
}

# Main monitoring loop
while true; do
    clear
    echo "╔════════════════════════════════════════════════════════════════╗"
    echo "║                    Episode Progress Monitor                    ║"
    echo "╚════════════════════════════════════════════════════════════════╝"
    echo ""
    
    # Get current progress
    local progress=$(get_progress)
    local api_rate=$(get_api_rate)
    
    if [[ -n "$progress" ]]; then
        echo "📈 Current Progress:"
        echo "   $progress"
        echo ""
        
        # Extract numbers for calculations
        if [[ $progress =~ Processing\ episode\ ([0-9]+)/([0-9]+).*\(([0-9.]+)%\) ]]; then
            current=${BASH_REMATCH[1]}
            total=${BASH_REMATCH[2]}
            percent=${BASH_REMATCH[3]}
            remaining=$((total - current))
            
            echo "📊 Summary:"
            echo "   • Completed: $current episodes"
            echo "   • Remaining: $remaining episodes"
            echo "   • Total: $total episodes"
            echo "   • Progress: $percent%"
            echo ""
            
            # Estimate completion time based on rate
            if [[ $api_rate -gt 0 ]]; then
                # Rough estimate: ~3-5 API calls per episode
                avg_calls_per_episode=4
                episodes_per_minute=$(echo "scale=2; $api_rate / $avg_calls_per_episode" | bc -l 2>/dev/null || echo "~1")
                if [[ -n "$episodes_per_minute" && "$episodes_per_minute" != "0" ]]; then
                    eta_minutes=$(echo "scale=0; $remaining / $episodes_per_minute" | bc -l 2>/dev/null || echo "unknown")
                    echo "⏱️  Estimated Time Remaining: ~$eta_minutes minutes"
                fi
            fi
        fi
    else
        echo "❓ No recent progress found"
    fi
    
    echo ""
    echo "🔄 Activity:"
    echo "   • API calls (last minute): $api_rate"
    
    if is_processing; then
        echo "   • Status: ✅ Actively processing"
    else
        echo "   • Status: ⚠️  No recent activity detected"
    fi
    
    echo ""
    echo "🔍 Latest logs:"
    docker logs pd-graphiti-service --tail 3 2>/dev/null | \
    grep -E "(Processing episode|Resolved Edge)" | \
    tail -2 | \
    sed 's/^/   /'
    
    echo ""
    echo "Press Ctrl+C to stop monitoring..."
    sleep 10
done