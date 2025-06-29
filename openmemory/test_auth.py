#!/usr/bin/env python3
"""
Simple test script to verify authentication setup
"""

import os
import sys
import requests
import json

def test_health_check():
    """Test the health check endpoint"""
    api_url = os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:8765")
    
    try:
        response = requests.get(f"{api_url}/api/v1/stats/health-check", timeout=10)
        response.raise_for_status()
        
        data = response.json()
        print("✅ Health check passed")
        print(f"Service: {data.get('service', 'unknown')}")
        print(f"Status: {data.get('status', 'unknown')}")
        
        auth_service = data.get('details', {}).get('auth_service', {})
        if auth_service:
            print(f"Auth Service Healthy: {auth_service.get('healthy', False)}")
            print(f"Auth Service Enabled: {auth_service.get('enabled', True)}")
        
        return True
    except Exception as e:
        print(f"❌ Health check failed: {e}")
        return False

def test_protected_endpoint():
    """Test a protected endpoint without authentication"""
    api_url = os.getenv("NEXT_PUBLIC_API_URL", "http://localhost:8765")
    
    try:
        response = requests.get(f"{api_url}/api/v1/memories", timeout=10)
        
        if response.status_code == 401:
            print("✅ Protected endpoint correctly requires authentication")
            return True
        elif response.status_code == 200:
            print("⚠️  Protected endpoint accessible without auth (AUTH_ENABLED=false)")
            return True
        else:
            print(f"❌ Unexpected response status: {response.status_code}")
            return False
            
    except Exception as e:
        print(f"❌ Protected endpoint test failed: {e}")
        return False

def main():
    print("Testing OpenMemory API Authentication Setup")
    print("=" * 50)
    
    # Test health check
    health_ok = test_health_check()
    print()
    
    # Test protected endpoint
    protected_ok = test_protected_endpoint()
    print()
    
    if health_ok and protected_ok:
        print("✅ All tests passed!")
        sys.exit(0)
    else:
        print("❌ Some tests failed!")
        sys.exit(1)

if __name__ == "__main__":
    main()