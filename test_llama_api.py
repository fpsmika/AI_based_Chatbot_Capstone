import requests
import json
import subprocess
import time
from threading import Thread
import sys

# Configuration
OPENROUTER_API_KEY = "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"  # Replace with your actual key
LLAMA_MODEL = "meta-llama/llama-4-scout:free"
FASTAPI_HOST = "http://localhost:8000"

class FastAPIServer:
    def __init__(self):
        self.process = None

    def start(self):
        """Start FastAPI server using python -m uvicorn"""
        self.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        # Wait for server to start
        time.sleep(5)
        return self.process

    def stop(self):
        """Stop the FastAPI server"""
        if self.process:
            self.process.terminate()
            try:
                self.process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self.process.kill()

def test_llama_api_direct():
    """Test direct API call to OpenRouter"""
    print("\n🔍 Testing Llama API directly...")
    
    headers = {
        "Authorization": f"Bearer {OPENROUTER_API_KEY}",
        "Content-Type": "application/json"
    }
    
    test_prompt = "Hello! Please respond with a brief greeting about supply chain management."
    
    try:
        response = requests.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json={
                "model": LLAMA_MODEL,
                "messages": [{"role": "user", "content": test_prompt}],
                "max_tokens": 100
            },
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            result = response.json()
            print("✅ API Response Received")
            print(f"🤖 Llama Response: {result['choices'][0]['message']['content'][:100]}...")
            return True
        else:
            print(f"❌ API Error: {response.status_code}")
            print(f"Error Details: {response.text[:200]}...")
            return False
            
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return False

def test_llama_service():
    """Test the LlamaService implementation"""
    print("\n🔍 Testing LlamaService class...")
    
    try:
        # Import your service (make sure PYTHONPATH is set correctly)
        from app.services.llama_service import LlamaService
        
        # Test query
        test_prompt = "What are the key challenges in supply chain management?"
        response = LlamaService.query(test_prompt, max_tokens=150)
        
        print(f"✅ Service Response: {response[:200]}...")  # Print first 200 chars
        return True
        
    except ImportError as e:
        print(f"❌ Import Error: {str(e)}")
        print("Make sure you're running from the project root directory")
        return False
    except Exception as e:
        print(f"❌ Service Error: {str(e)}")
        return False

def test_fastapi_endpoint():
    """Test the FastAPI chat endpoint"""
    print("\n🔍 Testing FastAPI chat endpoint...")
    
    try:
        response = requests.post(
            f"{FASTAPI_HOST}/chat",
            json={"message": "Explain supply chain optimization"},
            timeout=10
        )
        
        if response.status_code == 200:
            result = response.json()
            print("✅ FastAPI Response:")
            print(f"Response: {result.get('response', '')[:100]}...")
            print(f"Suggestions: {result.get('suggestions', [])}")
            return True
        else:
            print(f"❌ FastAPI Error: {response.status_code}")
            print(f"Error Details: {response.text[:200]}...")
            return False
            
    except requests.exceptions.ConnectionError:
        print("❌ Connection Error: Is the FastAPI server running?")
        return False
    except Exception as e:
        print(f"❌ Exception: {str(e)}")
        return False

def run_tests():
    """Run all tests with proper server management"""
    server = FastAPIServer()
    test_results = {}
    
    try:
        print("🚀 Starting FastAPI server...")
        server.start()
        
        print("\n" + "="*50)
        print("Starting Llama API Integration Tests")
        print("="*50 + "\n")
        
        # Run tests
        test_results['direct_api'] = test_llama_api_direct()
        test_results['service'] = test_llama_service()
        test_results['fastapi'] = test_fastapi_endpoint()
        
        # Print summary
        print("\n" + "="*50)
        print("📊 Test Results Summary")
        print("="*50)
        print(f"1. Direct API Test: {'✅ PASS' if test_results['direct_api'] else '❌ FAIL'}")
        print(f"2. LlamaService Test: {'✅ PASS' if test_results['service'] else '❌ FAIL'}")
        print(f"3. FastAPI Endpoint Test: {'✅ PASS' if test_results['fastapi'] else '❌ FAIL'}")
        
        if all(test_results.values()):
            print("\n🎉 All tests passed successfully!")
            return True
        else:
            print("\n⚠️ Some tests failed. See above for details.")
            return False
            
    finally:
        print("\n🛑 Stopping FastAPI server...")
        server.stop()

if __name__ == "__main__":
    # Add project root to PYTHONPATH
    import os
    import sys
    sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    
    if not run_tests():
        sys.exit(1)  # Exit with error code if any test failed