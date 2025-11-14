#!/bin/bash
# Comprehensive Test Runner for Streams Prefetcher
# Runs ALL tests: unit tests, host-based integration tests, and Docker-based integration tests

set -e

# Color codes
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
RED='\033[0;31m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo "═══════════════════════════════════════════════════════════════"
echo "  Streams Prefetcher - Comprehensive Test Suite"
echo "═══════════════════════════════════════════════════════════════"
echo ""

# Function to print section headers
print_section() {
    echo ""
    echo -e "${BLUE}▶ $1${NC}"
    echo "───────────────────────────────────────────────────────────────"
}

# Function to print results
print_result() {
    local status=$1
    local message=$2
    if [ "$status" = "success" ]; then
        echo -e "${GREEN}✓ $message${NC}"
    elif [ "$status" = "warning" ]; then
        echo -e "${YELLOW}⚠ $message${NC}"
    else
        echo -e "${RED}✗ $message${NC}"
    fi
}

# Track overall results
total_tests=0
total_passed=0
total_failed=0
total_skipped=0

# ========================================================================
# PHASE 1: Unit Tests (no container required)
# ========================================================================
print_section "PHASE 1: Unit Tests (Host-based, no container required)"

echo "Running unit tests..."
if pytest tests/test_item_class.py tests/test_addon_objects.py tests/test_ui_features.py -v --tb=short > /tmp/unit_tests.log 2>&1; then
    # Parse results
    unit_result=$(tail -1 /tmp/unit_tests.log)
    print_result "success" "Unit tests completed"
    echo "   $unit_result"

    # Extract counts (assuming format like "X passed, Y skipped, Z failed")
    passed=$(echo "$unit_result" | grep -oP '\d+ passed' | grep -oP '\d+' || echo "0")
    skipped=$(echo "$unit_result" | grep -oP '\d+ skipped' | grep -oP '\d+' || echo "0")
    failed=$(echo "$unit_result" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")

    total_passed=$((total_passed + passed))
    total_skipped=$((total_skipped + skipped))
    total_failed=$((total_failed + failed))
    total_tests=$((total_tests + passed + skipped + failed))
else
    print_result "error" "Unit tests encountered errors"
    cat /tmp/unit_tests.log | tail -20
fi

# ========================================================================
# PHASE 2: Host-based Integration Tests (requires container on localhost:5000)
# ========================================================================
print_section "PHASE 2: Integration Tests (Host-based, requires container)"

# Check if container is accessible
if docker exec streams-prefetcher python3 -c "import requests; requests.get('http://localhost:5000/api/health', timeout=2)" > /dev/null 2>&1; then
    echo "Container is accessible - running host-based integration tests..."

    if pytest tests/test_integration.py tests/test_api_endpoints.py tests/test_episode_based_limiting.py -v --tb=short > /tmp/host_integration_tests.log 2>&1; then
        host_result=$(tail -1 /tmp/host_integration_tests.log)
        print_result "success" "Host-based integration tests completed"
        echo "   $host_result"

        passed=$(echo "$host_result" | grep -oP '\d+ passed' | grep -oP '\d+' || echo "0")
        skipped=$(echo "$host_result" | grep -oP '\d+ skipped' | grep -oP '\d+' || echo "0")
        failed=$(echo "$host_result" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")

        total_passed=$((total_passed + passed))
        total_skipped=$((total_skipped + skipped))
        total_failed=$((total_failed + failed))
        total_tests=$((total_tests + passed + skipped + failed))
    else
        print_result "warning" "Host-based integration tests had errors"
        cat /tmp/host_integration_tests.log | tail -20
    fi
else
    print_result "warning" "Container not accessible - skipping host-based integration tests"
    echo "   To run these tests, ensure streams-prefetcher container is running:"
    echo "   cd /opt/docker && docker compose --profile streams-prefetcher up -d"
fi

# ========================================================================
# PHASE 3: Docker-based Integration Tests (recommended)
# ========================================================================
print_section "PHASE 3: Docker-based Integration Tests (Recommended)"

echo "Building test runner container and running Docker-based integration tests..."
if ./run_integration_tests.sh > /tmp/docker_integration_tests.log 2>&1; then
    docker_result=$(grep -A 2 "short test summary" /tmp/docker_integration_tests.log | tail -1 || tail -1 /tmp/docker_integration_tests.log)
    print_result "success" "Docker-based integration tests completed"
    echo "   $docker_result"

    passed=$(echo "$docker_result" | grep -oP '\d+ passed' | grep -oP '\d+' || echo "0")
    skipped=$(echo "$docker_result" | grep -oP '\d+ skipped' | grep -oP '\d+' || echo "0")
    failed=$(echo "$docker_result" | grep -oP '\d+ failed' | grep -oP '\d+' || echo "0")

    total_passed=$((total_passed + passed))
    total_skipped=$((total_skipped + skipped))
    total_failed=$((total_failed + failed))
    total_tests=$((total_tests + passed + skipped + failed))
else
    print_result "warning" "Docker-based integration tests had errors"
    cat /tmp/docker_integration_tests.log | tail -30
fi

# ========================================================================
# FINAL SUMMARY
# ========================================================================
echo ""
echo "═══════════════════════════════════════════════════════════════"
echo "  Final Results"
echo "═══════════════════════════════════════════════════════════════"
echo ""
echo -e "Total Tests:    ${BLUE}$total_tests${NC}"
echo -e "Passed:         ${GREEN}$total_passed${NC}"
echo -e "Skipped:        ${YELLOW}$total_skipped${NC}"
echo -e "Failed:         ${RED}$total_failed${NC}"
echo ""

if [ $total_failed -eq 0 ]; then
    echo -e "${GREEN}✓ All tests passed!${NC}"
    exit 0
else
    echo -e "${RED}✗ Some tests failed${NC}"
    echo ""
    echo "Review log files:"
    echo "  • /tmp/unit_tests.log"
    echo "  • /tmp/host_integration_tests.log"
    echo "  • /tmp/docker_integration_tests.log"
    exit 1
fi
