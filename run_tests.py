#!/usr/bin/env python3
"""
Test runner script for streams-prefetcher.
Provides convenient ways to run different test categories.
"""
import subprocess
import sys
import argparse


def run_command(cmd):
    """Run a command and return the exit code."""
    result = subprocess.run(cmd, shell=True)
    return result.returncode


def run_unit_tests():
    """Run only unit tests (no container required)."""
    print("🧪 Running Unit Tests...")
    cmd = "python3 -m pytest tests/test_item_class.py tests/test_ui_features.py -v"
    return run_command(cmd)


def run_integration_tests():
    """Run integration tests (requires running container)."""
    print("🔗 Running Integration Tests...")
    print("⚠️  Make sure the streams-prefetcher container is running!")
    cmd = "python3 -m pytest tests/test_integration.py tests/test_episode_based_limiting.py -v -s"
    return run_command(cmd)


def run_api_tests():
    """Run API endpoint tests (requires running container)."""
    print("🌐 Running API Tests...")
    print("⚠️  Make sure the streams-prefetcher container is running!")
    cmd = "python3 -m pytest tests/test_api_endpoints.py -v -s"
    return run_command(cmd)


def run_all_tests():
    """Run all tests."""
    print("🚀 Running All Tests...")
    cmd = "python3 -m pytest tests/ -v"
    return run_command(cmd)


def run_failed_tests():
    """Run only previously failed tests."""
    print("❌ Running Failed Tests...")
    cmd = "python3 -m pytest --lf -v"
    return run_command(cmd)


def run_coverage():
    """Run tests with coverage report."""
    print("📊 Running Tests with Coverage...")
    try:
        cmd = "python3 -m pytest tests/ --cov=src --cov-report=term-missing -v"
        return run_command(cmd)
    except ImportError:
        print("❌ Coverage not installed. Install with: pip install pytest-cov")
        return 1


def main():
    parser = argparse.ArgumentParser(description="Test runner for streams-prefetcher")
    parser.add_argument(
        "category",
        choices=['unit', 'integration', 'api', 'all', 'failed', 'coverage'],
        help="Test category to run"
    )
    args = parser.parse_args()

    if args.category == 'unit':
        exit_code = run_unit_tests()
    elif args.category == 'integration':
        exit_code = run_integration_tests()
    elif args.category == 'api':
        exit_code = run_api_tests()
    elif args.category == 'all':
        exit_code = run_all_tests()
    elif args.category == 'failed':
        exit_code = run_failed_tests()
    elif args.category == 'coverage':
        exit_code = run_coverage()
    else:
        print(f"Unknown category: {args.category}")
        exit_code = 1

    sys.exit(exit_code)


if __name__ == "__main__":
    main()