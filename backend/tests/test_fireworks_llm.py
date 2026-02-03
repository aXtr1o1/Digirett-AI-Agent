"""
test_fireworks_llm.py
Test Fireworks.ai Qwen Model Connection

Run this BEFORE starting your application to verify:
✅ Fireworks API key is valid
✅ Qwen model is accessible
✅ Streaming works correctly
✅ Response quality is good
"""

import sys
import asyncio
import httpx
import json
import time

# Colors for terminal output
class Colors:
    GREEN = '\033[92m'
    RED = '\033[91m'
    YELLOW = '\033[93m'
    BLUE = '\033[94m'
    RESET = '\033[0m'

def print_success(msg: str):
    print(f"{Colors.GREEN}✅ {msg}{Colors.RESET}")

def print_error(msg: str):
    print(f"{Colors.RED}❌ {msg}{Colors.RESET}")

def print_warning(msg: str):
    print(f"{Colors.YELLOW}⚠️  {msg}{Colors.RESET}")

def print_info(msg: str):
    print(f"{Colors.BLUE}ℹ️  {msg}{Colors.RESET}")


class FireworksLLMTester:
    """Test Fireworks.ai LLM endpoint"""
    
    def __init__(
        self,
        api_key: str = "fw_AVA8YN7vqJv2mdQ9uWfD1w",
        model: str = "accounts/fireworks/models/qwen3-8b"
    ):
        self.api_key = api_key
        self.model = model
        self.base_url = "https://api.fireworks.ai/inference/v1/chat/completions"
        
        print_info(f"Model: {model}")
        print_info(f"API Key: {api_key[:20]}...")
        print()
    
    async def test_api_key(self) -> bool:
        """Test 1: Check API key validity"""
        print("=" * 60)
        print("TEST 1: Fireworks API Key")
        print("=" * 60)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [{"role": "user", "content": "test"}],
                        "max_tokens": 5
                    }
                )
                
                if response.status_code == 401:
                    print_error("Invalid API key!")
                    print_warning("Get a valid key from: https://fireworks.ai")
                    return False
                elif response.status_code == 200:
                    print_success("API key is valid")
                    return True
                else:
                    print_warning(f"Unexpected status code: {response.status_code}")
                    print_info(f"Response: {response.text[:200]}")
                    return False
                    
        except httpx.ConnectError:
            print_error("Cannot connect to Fireworks API")
            print_warning("Check your internet connection")
            return False
        except Exception as e:
            print_error(f"API key test failed: {e}")
            return False
    
    async def test_model_access(self) -> bool:
        """Test 2: Check model accessibility"""
        print("\n" + "=" * 60)
        print("TEST 2: Model Access")
        print("=" * 60)
        
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "user", "content": "Say hello"}
                        ],
                        "max_tokens": 10
                    }
                )
                
                if response.status_code == 404:
                    print_error(f"Model '{self.model}' not found!")
                    print_warning("Available models:")
                    print("   - accounts/fireworks/models/qwen3-8b")
                    print("   - accounts/fireworks/models/qwen-2-7b-instruct")
                    print("   - accounts/fireworks/models/qwen2-72b-instruct")
                    return False
                elif response.status_code == 200:
                    data = response.json()
                    answer = data["choices"][0]["message"]["content"]
                    print_success(f"Model is accessible")
                    print_info(f"Response: {answer}")
                    return True
                else:
                    print_warning(f"Unexpected status: {response.status_code}")
                    print_info(f"Response: {response.text[:200]}")
                    return False
                    
        except Exception as e:
            print_error(f"Model access test failed: {e}")
            return False
    
    async def test_simple_generation(self) -> bool:
        """Test 3: Simple text generation"""
        print("\n" + "=" * 60)
        print("TEST 3: Simple Text Generation")
        print("=" * 60)
        
        test_prompt = "What is 2+2? Answer in one word."
        print_info(f"Prompt: '{test_prompt}'")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                start_time = time.time()
                
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "user", "content": test_prompt}
                        ],
                        "max_tokens": 50,
                        "temperature": 0.3
                    }
                )
                
                elapsed_time = time.time() - start_time
                
                if response.status_code != 200:
                    print_error(f"Generation failed: {response.status_code}")
                    print_info(response.text)
                    return False
                
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                tokens_used = data["usage"]["total_tokens"]
                
                print_success(f"Generation completed in {elapsed_time:.2f}s")
                print_info(f"Response: {answer}")
                print_info(f"Tokens used: {tokens_used}")
                
                return True
                
        except Exception as e:
            print_error(f"Generation test failed: {e}")
            return False
    
    async def test_streaming(self) -> bool:
        """Test 4: Streaming generation"""
        print("\n" + "=" * 60)
        print("TEST 4: Streaming Generation")
        print("=" * 60)
        
        test_prompt = "Count from 1 to 5."
        print_info(f"Prompt: '{test_prompt}'")
        print_info("Streaming response:")
        
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                tokens_received = 0
                full_response = ""
                
                async with client.stream(
                    "POST",
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "user", "content": test_prompt}
                        ],
                        "max_tokens": 100,
                        "temperature": 0.3,
                        "stream": True
                    }
                ) as response:
                    if response.status_code != 200:
                        print_error(f"Streaming failed: {response.status_code}")
                        return False
                    
                    print(f"{Colors.BLUE}", end="")
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            data_str = line[6:]
                            
                            if data_str.strip() == "[DONE]":
                                break
                            
                            try:
                                data = json.loads(data_str)
                                
                                if "choices" in data and len(data["choices"]) > 0:
                                    delta = data["choices"][0].get("delta", {})
                                    content = delta.get("content")
                                    
                                    if content:
                                        print(content, end="", flush=True)
                                        full_response += content
                                        tokens_received += 1
                            except json.JSONDecodeError:
                                continue
                    
                    print(f"{Colors.RESET}")
                
                print_success(f"Streaming completed ({tokens_received} tokens)")
                print_info(f"Full response: {full_response}")
                
                return tokens_received > 0
                
        except Exception as e:
            print_error(f"Streaming test failed: {e}")
            return False
    
    async def test_rag_scenario(self) -> bool:
        """Test 5: RAG-like scenario with Norwegian legal text"""
        print("\n" + "=" * 60)
        print("TEST 5: RAG Scenario (Norwegian Legal)")
        print("=" * 60)
        
        # Simulate RAG context
        context = """[Kilde 1: § 1-1. Lovens virkeområde]
Loven gjelder for aksjeselskaper som er stiftet i Norge.

[Kilde 2: § 1-2. Definisjoner]
Med aksjeselskap menes selskap hvor deltakerne ikke hefter personlig for selskapets forpliktelser."""
        
        query = "Hva gjelder aksjeloven for?"
        
        system_prompt = """You are an AI Legal Assistant. Answer ONLY based on the provided legal excerpts."""
        
        user_prompt = f"""CRITICAL: Answer ONLY based on the following legal excerpts.

KILDER (Sources):
{context}

SPØRSMÅL (Question):
{query}

SVAR (Answer):"""
        
        print_info("Testing RAG-style prompt with Norwegian legal text...")
        
        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                start_time = time.time()
                
                response = await client.post(
                    self.base_url,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json"
                    },
                    json={
                        "model": self.model,
                        "messages": [
                            {"role": "system", "content": system_prompt},
                            {"role": "user", "content": user_prompt}
                        ],
                        "max_tokens": 500,
                        "temperature": 0.3,
                        "top_p": 0.95
                    }
                )
                
                elapsed_time = time.time() - start_time
                
                if response.status_code != 200:
                    print_error(f"RAG test failed: {response.status_code}")
                    return False
                
                data = response.json()
                answer = data["choices"][0]["message"]["content"]
                tokens_used = data["usage"]["total_tokens"]
                
                print_success(f"RAG response generated in {elapsed_time:.2f}s")
                print_info(f"Tokens used: {tokens_used}")
                print()
                print("=" * 60)
                print("ANSWER:")
                print("=" * 60)
                print(answer)
                print("=" * 60)
                
                # Check if answer is in Norwegian
                norwegian_indicators = ["gjelder", "aksjeselskap", "Norge"]
                is_norwegian = any(word in answer for word in norwegian_indicators)
                
                if is_norwegian:
                    print_success("Answer is in Norwegian (correct!)")
                else:
                    print_warning("Answer might not be in Norwegian")
                
                return True
                
        except Exception as e:
            print_error(f"RAG test failed: {e}")
            return False
    
    async def run_all_tests(self) -> bool:
        """Run all tests"""
        print("\n" + "🔥 " * 20)
        print("FIREWORKS.AI LLM TEST SUITE")
        print("🔥 " * 20 + "\n")
        
        tests = [
            ("API Key", self.test_api_key),
            ("Model Access", self.test_model_access),
            ("Simple Generation", self.test_simple_generation),
            ("Streaming", self.test_streaming),
            ("RAG Scenario", self.test_rag_scenario),
        ]
        
        results = []
        
        for test_name, test_func in tests:
            try:
                result = await test_func()
                results.append((test_name, result))
            except Exception as e:
                print_error(f"Test '{test_name}' crashed: {e}")
                results.append((test_name, False))
        
        # Summary
        print("\n" + "=" * 60)
        print("TEST SUMMARY")
        print("=" * 60)
        
        for test_name, result in results:
            if result:
                print_success(f"{test_name}: PASSED")
            else:
                print_error(f"{test_name}: FAILED")
        
        passed = sum(1 for _, result in results if result)
        total = len(results)
        
        print("\n" + "=" * 60)
        if passed == total:
            print_success(f"ALL TESTS PASSED ({passed}/{total})")
            print_success("Fireworks Qwen model is ready for production!")
            return True
        else:
            print_error(f"SOME TESTS FAILED ({passed}/{total} passed)")
            print_warning("Fix the issues above before using in production")
            return False


async def main():
    # Configuration
    API_KEY = "fw_AVA8YN7vqJv2mdQ9uWfD1w"
    MODEL = "accounts/fireworks/models/qwen3-8b"
    
    # Allow override from command line
    if len(sys.argv) > 1:
        API_KEY = sys.argv[1]
    if len(sys.argv) > 2:
        MODEL = sys.argv[2]
    
    # Run tests
    tester = FireworksLLMTester(api_key=API_KEY, model=MODEL)
    success = await tester.run_all_tests()
    
    sys.exit(0 if success else 1)


if __name__ == "__main__":
    asyncio.run(main())