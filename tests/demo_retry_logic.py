"""
Demonstration of the retry logic with exponential backoff.

This script shows how the retry mechanism works when creating Discord Scheduled Events.
"""

import asyncio
from datetime import datetime


async def simulate_retry_with_backoff(max_retries=3):
    """
    Simulate the retry logic with exponential backoff.
    
    This demonstrates the timing and behavior of the retry mechanism.
    """
    print("=== Discord API Retry Logic Demonstration ===\n")
    print(f"Configuration: {max_retries} maximum retries with exponential backoff\n")
    
    for attempt in range(max_retries):
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Attempt {attempt + 1}/{max_retries}")
        
        # Simulate API call (would fail in real scenario)
        print(f"  → Attempting to create scheduled event...")
        await asyncio.sleep(0.1)  # Simulate API call time
        print(f"  ✗ Failed: HTTPException (Server error)")
        
        if attempt < max_retries - 1:
            # Calculate exponential backoff
            backoff_time = 2 ** attempt
            print(f"  ⏳ Waiting {backoff_time} second(s) before retry...")
            await asyncio.sleep(backoff_time)
            print()
        else:
            print(f"\n❌ All {max_retries} attempts failed")
            print("  → Event status set to 'expired'")
            print("  → Winning date/time preserved in database")
            print("  → Failure notification sent to channel")


async def simulate_successful_retry():
    """
    Simulate a successful retry on the second attempt.
    """
    print("\n\n=== Successful Retry Scenario ===\n")
    print("Configuration: Retry succeeds on attempt 2\n")
    
    for attempt in range(3):
        print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Attempt {attempt + 1}/3")
        
        print(f"  → Attempting to create scheduled event...")
        await asyncio.sleep(0.1)
        
        if attempt == 1:
            # Success on second attempt
            print(f"  ✓ Success! Scheduled event created")
            print(f"  → Event status set to 'scheduled'")
            print(f"  → Poll message updated with results")
            break
        else:
            print(f"  ✗ Failed: HTTPException (Rate limited)")
            backoff_time = 2 ** attempt
            print(f"  ⏳ Waiting {backoff_time} second(s) before retry...")
            await asyncio.sleep(backoff_time)
            print()


async def simulate_permission_error():
    """
    Simulate a permission error (no retry).
    """
    print("\n\n=== Permission Error Scenario ===\n")
    print("Configuration: Forbidden error (no retry)\n")
    
    print(f"[{datetime.now().strftime('%H:%M:%S.%f')[:-3]}] Attempt 1/3")
    print(f"  → Attempting to create scheduled event...")
    await asyncio.sleep(0.1)
    print(f"  ✗ Failed: Forbidden (Missing permissions)")
    print(f"  ⚠️  Permission errors are not retried")
    print(f"  → Event status set to 'expired'")
    print(f"  → Failure notification sent with permission error message")


async def main():
    """Run all demonstrations."""
    print("This demonstration shows the retry logic for Discord API failures\n")
    print("=" * 60)
    
    # Scenario 1: All retries fail
    await simulate_retry_with_backoff(max_retries=3)
    
    # Scenario 2: Success on retry
    await simulate_successful_retry()
    
    # Scenario 3: Permission error (no retry)
    await simulate_permission_error()
    
    print("\n" + "=" * 60)
    print("\nKey Features:")
    print("  • Exponential backoff: 1s, 2s, 4s, 8s, ...")
    print("  • Permission errors don't retry (won't be fixed)")
    print("  • Event data preserved for manual recovery")
    print("  • Comprehensive logging at each step")
    print("  • Failure notifications sent to channel")


if __name__ == "__main__":
    asyncio.run(main())
