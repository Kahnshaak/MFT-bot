#!/usr/bin/env python3
"""
Test script for the Game Night Bot Web Dashboard.
Tests the basic functionality without requiring Discord OAuth.
"""

import asyncio
import aiohttp
import json
import sys
from pathlib import Path

# Add src to Python path
sys.path.append(str(Path(__file__).parent / "src"))

async def test_web_dashboard():
    """Test the web dashboard endpoints."""
    base_url = "http://localhost:8000"
    
    async with aiohttp.ClientSession() as session:
        print("🧪 Testing Game Night Bot Web Dashboard")
        print("=" * 50)
        
        # Test health endpoint
        print("\n1. Testing health endpoint...")
        try:
            async with session.get(f"{base_url}/api/health") as resp:
                if resp.status == 200:
                    data = await resp.json()
                    print(f"✅ Health check passed: {data['status']}")
                    print(f"   Database: {data.get('database', 'unknown')}")
                    print(f"   OAuth: {data.get('oauth', 'unknown')}")
                else:
                    print(f"❌ Health check failed: {resp.status}")
        except Exception as e:
            print(f"❌ Health check error: {e}")
        
        # Test login page (should redirect or show login)
        print("\n2. Testing login page...")
        try:
            async with session.get(f"{base_url}/auth/login", allow_redirects=False) as resp:
                if resp.status in [200, 503]:  # 503 if OAuth not configured
                    print(f"✅ Login page accessible: {resp.status}")
                else:
                    print(f"❌ Login page failed: {resp.status}")
        except Exception as e:
            print(f"❌ Login page error: {e}")
        
        # Test dashboard redirect (should redirect to login)
        print("\n3. Testing dashboard redirect...")
        try:
            async with session.get(f"{base_url}/", allow_redirects=False) as resp:
                if resp.status == 302:
                    location = resp.headers.get('Location', '')
                    if '/auth/login' in location:
                        print("✅ Dashboard correctly redirects to login")
                    else:
                        print(f"❌ Dashboard redirects to unexpected location: {location}")
                elif resp.status == 200:
                    print("✅ Dashboard accessible (user might be authenticated)")
                else:
                    print(f"❌ Dashboard failed: {resp.status}")
        except Exception as e:
            print(f"❌ Dashboard error: {e}")
        
        # Test API endpoints without authentication (should fail)
        print("\n4. Testing protected API endpoints...")
        protected_endpoints = [
            "/api/stats",
            "/api/events",
            "/api/monitoring/dashboard"
        ]
        
        for endpoint in protected_endpoints:
            try:
                async with session.get(f"{base_url}{endpoint}") as resp:
                    if resp.status == 401:
                        print(f"✅ {endpoint} correctly requires authentication")
                    elif resp.status == 200:
                        print(f"⚠️  {endpoint} accessible without auth (might be test mode)")
                    else:
                        print(f"❌ {endpoint} unexpected status: {resp.status}")
            except Exception as e:
                print(f"❌ {endpoint} error: {e}")
        
        # Test CSRF protection
        print("\n5. Testing CSRF protection...")
        try:
            # Try POST without CSRF token
            async with session.post(f"{base_url}/auth/logout") as resp:
                if resp.status == 403:
                    print("✅ CSRF protection working (POST blocked without token)")
                elif resp.status == 401:
                    print("✅ Authentication required for logout")
                else:
                    print(f"⚠️  Unexpected CSRF response: {resp.status}")
        except Exception as e:
            print(f"❌ CSRF test error: {e}")
        
        print("\n" + "=" * 50)
        print("🏁 Web dashboard tests completed!")
        print("\nTo fully test authentication:")
        print("1. Configure Discord OAuth credentials in .env")
        print("2. Start the web dashboard: python web/app.py")
        print("3. Visit http://localhost:8000 and test login flow")


if __name__ == "__main__":
    asyncio.run(test_web_dashboard())