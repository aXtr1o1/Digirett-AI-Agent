"""
execute_test_queries.py

ACTUAL TEST EXECUTION - Runs real queries against backend and gets LLM responses.

This script:
1. Uploads test documents via API
2. Executes all 20 test queries
3. Captures real LLM-generated answers
4. Displays results in terminal
5. Saves results to JSON file

Usage:
    python execute_test_queries.py

Prerequisites:
    - Backend server running on http://localhost:8000
    - Test documents available in test_docs/
    - .env file configured with API keys
"""

import asyncio
import json
import aiohttp
import os
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import logging

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(levelname)s | %(asctime)s | %(message)s",
)
logger = logging.getLogger(__name__)

# Color codes for terminal
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    WARNING = '\033[93m'
    FAIL = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class QueryExecutor:
    """Execute test queries against live backend."""
    
    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url
        self.conversation_id = None
        self.user_id = "2a06144d-4675-4c38-b7f8-13c02da91af5"
        self.test_docs_dir = Path("test_docs")
        self.test_scenarios = self._load_scenarios()
        self.results = {
            "execution_time": datetime.now().isoformat(),
            "backend_url": backend_url,
            "scenarios": []
        }
    
    def _load_scenarios(self) -> Dict[str, Any]:
        """Load test scenarios from JSON."""
        scenarios_file = Path("test_scenarios.json")
        if not scenarios_file.exists():
            logger.error(f"❌ Test scenarios file not found: {scenarios_file}")
            sys.exit(1)
        
        with open(scenarios_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def print_header(self, text: str, level: int = 1) -> None:
        """Print formatted header."""
        if level == 1:
            print(f"\n{Colors.BOLD}{Colors.HEADER}{'='*100}")
            print(f"{text:^100}")
            print(f"{'='*100}{Colors.ENDC}\n")
        elif level == 2:
            print(f"\n{Colors.BOLD}{Colors.CYAN}{'-'*100}")
            print(f"{text}")
            print(f"{'-'*100}{Colors.ENDC}\n")
    
    def print_status(self, status: str, message: str) -> None:
        """Print status message."""
        icons = {
            "info": "ℹ️ ",
            "success": "✅ ",
            "warning": "⚠️ ",
            "error": "❌ ",
            "debug": "🐛 ",
            "check": "✓ ",
        }
        
        colors = {
            "info": Colors.BLUE,
            "success": Colors.GREEN,
            "warning": Colors.WARNING,
            "error": Colors.FAIL,
            "debug": Colors.CYAN,
            "check": Colors.GREEN,
        }
        
        icon = icons.get(status, "→ ")
        color = colors.get(status, "")
        
        print(f"{color}{icon}{message}{Colors.ENDC}")
    
    async def check_backend(self) -> bool:
        """Check if backend is running."""
        try:
            async with aiohttp.ClientSession() as session:
                async with session.get(f"{self.backend_url}/api/v1/health") as resp:
                    if resp.status == 200:
                        self.print_status("success", f"Backend is running on {self.backend_url}")
                        return True
                    else:
                        self.print_status("error", f"Backend returned status {resp.status}")
                        return False
        except Exception as exc:
            self.print_status("error", f"Cannot connect to backend: {exc}")
            return False
    
    async def create_conversation(self) -> bool:
        """Create a new conversation session."""
        try:
            async with aiohttp.ClientSession() as session:
                payload = {
                    "user_id": self.user_id,
                    "title": "Test Document Query Session"
                }
                async with session.post(
                    f"{self.backend_url}/api/v1/conversations",
                    json=payload
                ) as resp:
                    if resp.status == 200:
                        data = await resp.json()
                        self.conversation_id = data.get("conversation_id")
                        self.print_status("success", f"Conversation created: {self.conversation_id}")
                        return True
                    else:
                        self.print_status("error", f"Failed to create conversation: {resp.status}")
                        return False
        except Exception as exc:
            self.print_status("error", f"Conversation creation failed: {exc}")
            return False
    
    async def upload_document(self, doc_path: Path) -> Optional[str]:
        """Upload a test document."""
        if not doc_path.exists():
            self.print_status("error", f"Document not found: {doc_path}")
            return None
        
        try:
            async with aiohttp.ClientSession() as session:
                with open(doc_path, 'rb') as f:
                    data = aiohttp.FormData()
                    data.add_field('conversation_id', self.conversation_id)
                    data.add_field('user_id', self.user_id)
                    data.add_field('file', f, filename=doc_path.name)
                    
                    async with session.post(
                        f"{self.backend_url}/api/v1/documents/upload",
                        data=data
                    ) as resp:
                        if resp.status == 200:
                            result = await resp.json()
                            doc_id = result.get("document_id")
                            self.print_status("success", f"Uploaded: {doc_path.name} ({result.get('char_count')} chars)")
                            return doc_id
                        else:
                            error = await resp.text()
                            self.print_status("error", f"Upload failed: {error[:100]}")
                            return None
        except Exception as exc:
            self.print_status("error", f"Upload error: {exc}")
            return None
    
    async def execute_query(self, query_text: str) -> Dict[str, Any]:
        """Execute a single query via WebSocket and get LLM response."""
        try:
            # Use HTTP POST instead of WebSocket for simplicity
            async with aiohttp.ClientSession() as session:
                payload = {
                    "query": query_text,
                    "conversation_id": self.conversation_id,
                    "user_id": self.user_id
                }
                
                # For WebSocket: ws://localhost:8000/api/v1/chat/ws
                # For HTTP SSE: POST to /api/v1/chat (if available)
                
                async with session.ws_connect(
                    f"{self.backend_url}/api/v1/chat/ws"
                ) as ws:
                    # Send query
                    await ws.send_json(payload)
                    
                    # Collect response
                    response = {
                        "query": query_text,
                        "events": [],
                        "full_answer": "",
                        "intent": None,
                        "language": None,
                        "score": 0.0,
                        "tokens_generated": 0,
                    }
                    
                    # Receive stream of events
                    async for msg in ws:
                        if msg.type == aiohttp.WSMsgType.TEXT:
                            event = json.loads(msg.data)
                            response["events"].append(event)
                            
                            # Extract fields
                            if event["type"] == "intent":
                                response["intent"] = event["data"].get("intent")
                                response["language"] = event["data"].get("language")
                            
                            elif event["type"] == "token":
                                response["full_answer"] += event["data"]
                            
                            elif event["type"] == "complete":
                                meta = event.get("metadata", {})
                                response["score"] = meta.get("score", 0.0)
                                response["tokens_generated"] = meta.get("tokens_generated", 0)
                                response["full_answer"] = meta.get("full_answer", response["full_answer"]).strip()
                        
                        elif msg.type == aiohttp.WSMsgType.ERROR:
                            response["error"] = str(msg)
                        
                        elif msg.type == aiohttp.WSMsgType.CLOSED:
                            break
                    
                    return response
        
        except Exception as exc:
            logger.exception(f"Query execution error: {exc}")
            return {
                "query": query_text,
                "error": str(exc),
                "events": []
            }
    
    def print_query_result(self, query_id: str, response: Dict[str, Any]) -> None:
        """Print query result in formatted way."""
        print(f"\n{Colors.BOLD}Query {query_id}{Colors.ENDC}")
        print(f"{Colors.CYAN}Q: {response.get('query', '')[:80]}...{Colors.ENDC}")
        
        # Intent and language
        intent = response.get("intent", "N/A")
        language = response.get("language", "N/A")
        print(f"\n  {Colors.BLUE}Intent:{Colors.ENDC} {intent} | {Colors.BLUE}Language:{Colors.ENDC} {language}")
        
        # Answer
        answer = response.get("full_answer", "")
        if answer:
            # Print first 300 chars
            preview = answer[:300] if len(answer) > 300 else answer
            print(f"\n  {Colors.GREEN}Answer:{Colors.ENDC}")
            print(f"  {preview}{'...' if len(answer) > 300 else ''}")
        
        # Score and tokens
        score = response.get("score", 0.0)
        tokens = response.get("tokens_generated", 0)
        print(f"\n  {Colors.BLUE}Score:{Colors.ENDC} {score:.2f} | {Colors.BLUE}Tokens:{Colors.ENDC} {tokens}")
        
        # Error if any
        if "error" in response:
            print(f"  {Colors.FAIL}Error: {response['error']}{Colors.ENDC}")
        
        print()
    
    async def run_all_tests(self) -> None:
        """Run all test scenarios with real LLM responses."""
        self.print_header("DIGIRETT DOCUMENT FEATURE TEST - LIVE EXECUTION", 1)
        
        # Check backend
        self.print_status("info", "Checking backend connection...")
        if not await self.check_backend():
            self.print_status("error", "Backend not running. Start it with: python main.py")
            return
        
        # Create conversation
        self.print_status("info", "Creating conversation session...")
        if not await self.create_conversation():
            self.print_status("error", "Failed to create conversation")
            return
        
        # Upload documents
        self.print_header("STEP 1: Uploading Test Documents", 2)
        uploaded_docs = []
        for doc_file in sorted(self.test_docs_dir.glob("*.docx")):
            doc_id = await self.upload_document(doc_file)
            if doc_id:
                uploaded_docs.append(doc_file.name)
        
        if not uploaded_docs:
            self.print_status("error", "Failed to upload documents")
            return
        
        self.print_status("success", f"Uploaded {len(uploaded_docs)} documents")
        
        # Execute queries
        self.print_header("STEP 2: Executing Test Queries", 2)
        
        scenarios = self.test_scenarios["test_scenarios"]
        
        for scenario_idx, scenario in enumerate(scenarios, 1):
            self.print_header(f"SCENARIO {scenario_idx}: {scenario['scenario_name']}", 2)
            self.print_status("info", scenario["description"])
            
            scenario_results = {
                "scenario_id": scenario["scenario_id"],
                "name": scenario["scenario_name"],
                "queries": []
            }
            
            for query_idx, query_def in enumerate(scenario["queries"], 1):
                query_id = query_def["query_id"]
                query_text = query_def["text"]
                language = query_def["language"]
                
                self.print_status("info", f"Executing Query {query_id} ({language.upper()})")
                print(f"  {Colors.CYAN}\"{query_text}\"{Colors.ENDC}")
                
                # Execute query
                response = await self.execute_query(query_text)
                
                # Print result
                self.print_query_result(query_id, response)
                
                # Store result
                scenario_results["queries"].append({
                    "query_id": query_id,
                    "query_text": query_text,
                    "language": language,
                    "response": response
                })
            
            self.results["scenarios"].append(scenario_results)
        
        # Summary
        self.print_summary()
    
    def print_summary(self) -> None:
        """Print execution summary."""
        self.print_header("TEST EXECUTION SUMMARY", 1)
        
        total_scenarios = len(self.results["scenarios"])
        total_queries = sum(len(s["queries"]) for s in self.results["scenarios"])
        
        successful = sum(
            1 for s in self.results["scenarios"] 
            for q in s["queries"] 
            if "error" not in q["response"]
        )
        
        self.print_status("info", f"Backend URL: {self.backend_url}")
        self.print_status("info", f"Conversation: {self.conversation_id}")
        self.print_status("info", f"Scenarios: {total_scenarios}")
        self.print_status("info", f"Total Queries: {total_queries}")
        self.print_status("success", f"Successful: {successful}/{total_queries}")
        
        # Save results to file
        results_file = Path("test_results.json")
        with open(results_file, 'w', encoding='utf-8') as f:
            json.dump(self.results, f, indent=2, ensure_ascii=False)
        
        self.print_status("success", f"Results saved to: {results_file}")
    
    async def main(self) -> None:
        """Main entry point."""
        try:
            await self.run_all_tests()
        except KeyboardInterrupt:
            self.print_status("warning", "Test interrupted by user")
        except Exception as exc:
            self.print_status("error", f"Unexpected error: {exc}")
            logger.exception("Unhandled exception")


async def main():
    """Main async entry point."""
    executor = QueryExecutor(backend_url="http://localhost:8000")
    await executor.main()


if __name__ == "__main__":
    asyncio.run(main())
