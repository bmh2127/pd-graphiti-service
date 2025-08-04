#!/bin/bash
# setup-paths.sh - Auto-detect and configure paths for Docker Compose

set -e

echo "🔍 Auto-detecting project paths..."

# Function to find a directory by searching upward from current location
find_project_root() {
    local target_dir="$1"
    local current_dir="$(pwd)"
    
    # Check current directory and parents up to 5 levels
    for i in {0..5}; do
        local search_path="$current_dir"
        for j in $(seq 1 $i); do
            search_path="$(dirname "$search_path")"
        done
        
        if [[ -d "$search_path/$target_dir" ]]; then
            echo "$search_path/$target_dir"
            return 0
        fi
    done
    
    return 1
}

# Function to find pd-target-identification exports directory
find_exports_dir() {
    local current_dir="$(pwd)"
    local fallback_path=""
    
    # Strategy 1: Check common locations relative to current directory (in priority order)
    local common_paths=(
        "../../pd-target-identification/src/exports"     # From docker/ to correct project (priority)
        "../../../pd-target-identification/src/exports"  # From deeper nesting
        "./pd-target-identification/src/exports"         # From same level
        "../pd-target-identification/src/exports"        # From parent directory (may be wrong project)
        "/Users/brandonhager/Documents/pd-target-identification/src/exports"  # Absolute fallback
        "./src/exports"                                   # Local src/exports
        "../src/exports"                                  # Parent src/exports
    )
    
    for path in "${common_paths[@]}"; do
        if [[ -d "$path" ]]; then
            # Check if directory has actual export content
            local export_count
            export_count=$(/usr/bin/find "$path" -maxdepth 1 -type d -name "graphiti_episodes_*" 2>/dev/null | /usr/bin/wc -l | /usr/bin/tr -d ' ')
            
            local abs_path
            abs_path=$(cd "$path" && pwd 2>/dev/null || echo "$path")
            
            # Prefer directories with content, but accept empty ones as fallback
            if [[ $export_count -gt 0 ]]; then
                echo "$abs_path"
                return 0
            elif [[ -z "$fallback_path" ]]; then
                fallback_path="$abs_path"
            fi
        fi
    done
    
    # Use fallback if we found an empty exports directory
    if [[ -n "$fallback_path" ]]; then
        echo "$fallback_path"
        return 0
    fi
    
    # Strategy 3: Search by directory name pattern
    local search_results
    search_results=$(/usr/bin/find "$current_dir/.." -maxdepth 3 -type d -name "exports" -path "*/pd-target-identification/src/exports" 2>/dev/null | head -1)
    
    if [[ -n "$search_results" ]]; then
        echo "$search_results"
        return 0
    fi
    
    return 1
}

# Main execution
main() {
    local exports_dir
    
    echo "Current directory: $(pwd)"
    
    # Try to find the exports directory
    if exports_dir=$(find_exports_dir); then
        echo "✅ Found exports directory: $exports_dir"
        
        # Verify it exists and has content
        if [[ -d "$exports_dir" ]]; then
            local export_count=$(/usr/bin/find "$exports_dir" -maxdepth 1 -type d -name "graphiti_episodes_*" 2>/dev/null | /usr/bin/wc -l | /usr/bin/tr -d ' ')
            echo "📁 Found $export_count export directories"
            
            # Update main .env file with export path (preserve existing config)
            local script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
            local main_env_file="$script_dir/../.env"
            local docker_env_file="$script_dir/.env"
            
            if [[ -f "$main_env_file" ]]; then
                # Update main .env file if it doesn't have EXPORT_SOURCE_PATH
                if ! grep -q "EXPORT_SOURCE_PATH" "$main_env_file"; then
                    echo "EXPORT_SOURCE_PATH=$exports_dir" >> "$main_env_file"
                    echo "✅ Added EXPORT_SOURCE_PATH to existing $main_env_file"
                else
                    echo "✅ EXPORT_SOURCE_PATH already exists in $main_env_file"
                fi
                
                # Create symlink in docker directory
                ln -sf "../.env" "$docker_env_file"
                echo "✅ Created symlink $docker_env_file -> ../.env"
            else
                # Create new .env file if none exists
                echo "EXPORT_SOURCE_PATH=$exports_dir" > "$docker_env_file"
                echo "✅ Created $docker_env_file with export path"
            fi
            
            # Also export for current shell session
            export EXPORT_SOURCE_PATH="$exports_dir"
            echo "🔧 Set EXPORT_SOURCE_PATH environment variable"
            
            return 0
        else
            echo "❌ Error: Directory exists but is not accessible: $exports_dir"
            return 1
        fi
    else
        echo "❌ Error: Could not find pd-target-identification/src/exports directory"
        echo ""
        echo "Please ensure:"
        echo "1. pd-target-identification project is cloned and accessible"
        echo "2. The src/exports directory exists"
        echo "3. You're running this from the pd-graphiti-service/docker directory"
        echo ""
        echo "You can manually set the path:"
        echo "export EXPORT_SOURCE_PATH=/path/to/pd-target-identification/src/exports"
        return 1
    fi
}

# Show usage if requested
if [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
    echo "Usage: $0 [--help]"
    echo ""
    echo "Auto-detects the pd-target-identification exports directory and configures"
    echo "the EXPORT_SOURCE_PATH environment variable for Docker Compose."
    echo ""
    echo "This script should be run from the pd-graphiti-service/docker directory."
    exit 0
fi

main "$@"