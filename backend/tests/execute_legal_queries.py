#!/usr/bin/env python3
"""
execute_legal_queries.py

LEGAL QUERIES EXECUTOR - Runs only legal/enriched VDB queries with full answer display.

This script:
1. Loads only 2 legal enriched VDB queries
2. Uploads test documents
3. Executes queries and displays FULL answers (not truncated)
4. Shows sources/citations clearly
5. Saves complete results to JSON

Usage:
    python execute_legal_queries.py

This is a specialized version for testing legal query results with citations.
"""

import json
import requests
import sys
from pathlib import Path
from typing import Dict, List, Any, Optional
from datetime import datetime
import time
import asyncio
import websockets

# Color codes for terminal output
class Colors:
    HEADER = '\033[95m'
    BLUE = '\033[94m'
    CYAN = '\033[96m'
    GREEN = '\033[92m'
    YELLOW = '\033[93m'
    RED = '\033[91m'
    ENDC = '\033[0m'
    BOLD = '\033[1m'
    UNDERLINE = '\033[4m'


class LegalQueryExecutor:
    """Execute legal queries with full answer display."""
    
    def __init__(self, backend_url: str = "http://localhost:8000"):
        self.backend_url = backend_url.rstrip('/')
        self.conversation_id = None
        self.user_id = "2a06144d-4675-4c38-b7f8-13c02da91af5"
        self.test_docs_dir = Path("test_docs")
        self.test_scenarios = self._load_scenarios()
        self.results = {
            "execution_time": datetime.now().isoformat(),
            "backend_url": backend_url,
            "test_type": "LEGAL_QUERIES_ONLY",
            "scenarios": []
        }
        self.uploaded_docs = []
        # Create event loop for async operations
        try:
            self.loop = asyncio.get_running_loop()
        except RuntimeError:
            self.loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.loop)
    
    def _load_scenarios(self) -> Dict[str, Any]:
        """Load legal test scenarios from JSON."""
        scenarios_file = Path("test_scenarios_legal_only.json")
        if not scenarios_file.exists():
            print(f"{Colors.RED}❌ Legal scenarios file not found: {scenarios_file}{Colors.ENDC}")
            print(f"   {Colors.YELLOW}Make sure test_scenarios_legal_only.json exists in this directory{Colors.ENDC}")
            sys.exit(1)
        
        with open(scenarios_file, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    def print_header(self, text: str, char: str = "=") -> None:
        """Print formatted header."""
        width = 100
        print(f"\n{Colors.BOLD}{Colors.HEADER}{char * width}")
        print(f"{text.center(width)}")
        print(f"{char * width}{Colors.ENDC}\n")
    
    def print_section(self, text: str) -> None:
        """Print section header."""
        print(f"\n{Colors.BOLD}{Colors.CYAN}📋 {text}{Colors.ENDC}")
        print(f"{Colors.CYAN}{'-' * 100}{Colors.ENDC}")
    
    def print_success(self, message: str) -> None:
        """Print success message."""
        print(f"{Colors.GREEN}✅ {message}{Colors.ENDC}")
    
    def print_info(self, message: str) -> None:
        """Print info message."""
        print(f"{Colors.BLUE}ℹ️  {message}{Colors.ENDC}")
    
    def print_error(self, message: str) -> None:
        """Print error message."""
        print(f"{Colors.RED}❌ {message}{Colors.ENDC}")
    
    def check_backend(self) -> bool:
        """Check if backend is running."""
        self.print_info(f"Checking backend connection at {self.backend_url}...")
        try:
            resp = requests.get(f"{self.backend_url}/api/v1/health", timeout=5)
            if resp.status_code == 200:
                self.print_success(f"Backend is running on {self.backend_url}")
                return True
            else:
                self.print_error(f"Backend returned status {resp.status_code}")
                return False
        except requests.exceptions.ConnectionError:
            self.print_error(f"Cannot connect to {self.backend_url}")
            self.print_info("Make sure to run: cd backend && python main.py")
            return False
        except Exception as exc:
            self.print_error(f"Connection error: {exc}")
            return False
    
    def create_conversation(self) -> bool:
        """Create a new conversation session."""
        self.print_info("Creating conversation session...")
        try:
            payload = {
                "user_id": self.user_id,
                "title": "Legal Queries Test"
            }
            resp = requests.post(
                f"{self.backend_url}/api/v1/conversations",
                json=payload,
                timeout=10
            )
            
            if resp.status_code == 200:
                data = resp.json()
                self.conversation_id = data.get("conversation_id")
                self.print_success(f"Conversation created: {self.conversation_id}")
                return True
            else:
                self.print_error(f"Failed to create conversation: {resp.text[:100]}")
                return False
        except Exception as exc:
            self.print_error(f"Error creating conversation: {exc}")
            return False
    
    def upload_documents(self) -> bool:
        """Upload all test documents."""
        self.print_section("Step 1: Uploading Test Documents")
        
        if not self.test_docs_dir.exists():
            self.print_error(f"Test documents directory not found: {self.test_docs_dir}")
            return False
        
        doc_files = sorted(self.test_docs_dir.glob("test_doc_*.docx"))
        if not doc_files:
            self.print_error("No test documents found in test_docs/")
            return False
        
        for doc_file in doc_files:
            try:
                with open(doc_file, 'rb') as f:
                    files = {
                        'file': (doc_file.name, f, 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'),
                    }
                    data = {
                        'conversation_id': self.conversation_id,
                        'user_id': self.user_id,
                    }
                    
                    resp = requests.post(
                        f"{self.backend_url}/api/v1/documents/upload",
                        files=files,
                        data=data,
                        timeout=30
                    )
                    
                    if resp.status_code == 200:
                        result = resp.json()
                        doc_id = result.get("document_id")
                        char_count = result.get("char_count", "?")
                        self.uploaded_docs.append(doc_id)
                        self.print_success(f"{doc_file.name} - {char_count} chars")
                    else:
                        self.print_error(f"Failed to upload {doc_file.name}: {resp.text[:100]}")
            except Exception as exc:
                self.print_error(f"Error uploading {doc_file.name}: {exc}")
        
        if self.uploaded_docs:
            self.print_success(f"Uploaded {len(self.uploaded_docs)} documents")
            return True
        else:
            self.print_error("No documents uploaded successfully")
            return False
    
    def execute_query(self, query_text: str, language: str = "english") -> Dict[str, Any]:
        """Execute a single query via WebSocket and get response."""
        try:
            result = self.loop.run_until_complete(self._execute_query_async(query_text, language))
            return result
        except Exception as exc:
            return {
                "error": True,
                "message": str(exc)
            }
    
    async def _execute_query_async(self, query_text: str, language: str = "english") -> Dict[str, Any]:
        """Async WebSocket query execution."""
        try:
            payload = {
                "query": query_text,
                "conversation_id": self.conversation_id,
                "user_id": self.user_id,
            }
            
            ws_url = self.backend_url.replace("http://", "ws://")
            
            async with websockets.connect(f"{ws_url}/api/v1/chat/ws") as ws:
                # Send query
                await ws.send(json.dumps(payload))
                
                # Collect response events
                full_answer = ""
                intent = "UNKNOWN"
                score = 0.0
                tokens = 0
                events = []
                sources = []
                
                while True:
                    try:
                        msg = await asyncio.wait_for(ws.recv(), timeout=60.0)
                        event = json.loads(msg)
                        events.append(event)
                        
                        if event.get("type") == "intent":
                            intent = event.get("data", {}).get("intent", "UNKNOWN")
                        
                        elif event.get("type") == "token":
                            full_answer += event.get("data", "")
                        
                        elif event.get("type") == "sources":
                            sources = event.get("data", [])
                        
                        elif event.get("type") == "complete":
                            metadata = event.get("metadata", {})
                            score = metadata.get("score", 0.0)
                            tokens = metadata.get("tokens_generated", 0)
                            break
                    
                    except asyncio.TimeoutError:
                        return {
                            "error": True,
                            "message": "WebSocket timeout waiting for completion"
                        }
                
                return {
                    "error": False,
                    "intent": intent,
                    "score": score,
                    "tokens_generated": tokens,
                    "full_answer": full_answer,
                    "sources": sources,
                    "events": events,
                }
        
        except Exception as exc:
            return {
                "error": True,
                "message": f"WebSocket error: {str(exc)}"
            }
    
    def run_test_scenarios(self) -> None:
        """Execute all legal test scenarios and queries."""
        self.print_header("LEGAL ENRICHED VDB QUERIES - FULL ANSWER DISPLAY")
        
        # Check backend
        if not self.check_backend():
            return
        
        # Create conversation
        if not self.create_conversation():
            return
        
        # Upload documents
        if not self.upload_documents():
            return
        
        # Execute scenarios
        self.print_section("Step 2: Executing Legal Queries")
        scenario_results = []
        
        for scenario_idx, scenario in enumerate(self.test_scenarios.get("test_scenarios", []), 1):
            scenario_id = scenario.get("scenario_id")
            scenario_name = scenario.get("scenario_name")
            
            print(f"\n{Colors.BOLD}{Colors.YELLOW}┌─ Scenario {scenario_id}: {scenario_name}{Colors.ENDC}")
            
            query_results = []
            
            for query_idx, query_def in enumerate(scenario.get("queries", []), 1):
                query_id = query_def.get("query_id")
                query_text = query_def.get("text")
                language = query_def.get("language", "english")
                
                print(f"\n{Colors.BOLD}{Colors.UNDERLINE}Query {query_id}:{Colors.ENDC}")
                print(f"{Colors.CYAN}  Language: {language}{Colors.ENDC}")
                print(f"{Colors.CYAN}  Question: {query_text}{Colors.ENDC}")
                print(f"\n  {Colors.YELLOW}🔄 Executing...{Colors.ENDC}", end="", flush=True)
                
                # Execute query
                response = self.execute_query(query_text, language)
                
                if response.get("error"):
                    print(f" {Colors.RED}❌{Colors.ENDC}")
                    print(f"  {Colors.RED}Error: {response.get('message')}{Colors.ENDC}")
                    query_result = {
                        "query_id": query_id,
                        "query_text": query_text,
                        "language": language,
                        "error": response.get('message'),
                        "success": False,
                    }
                else:
                    print(f" {Colors.GREEN}✅{Colors.ENDC}\n")
                    
                    # Extract relevant fields
                    answer = response.get("full_answer", "")
                    intent = response.get("intent", "UNKNOWN")
                    score = response.get("score", 0.0)
                    tokens = response.get("tokens_generated", 0)
                    sources = response.get("sources", [])
                    
                    # Display FULL answer (not truncated)
                    print(f"{Colors.BOLD}  Intent: {Colors.CYAN}{intent}{Colors.ENDC}")
                    print(f"{Colors.BOLD}  Score: {Colors.GREEN}{score:.2f}{Colors.ENDC} | Tokens: {Colors.BLUE}{tokens}{Colors.ENDC}\n")
                    
                    print(f"{Colors.BOLD}{Colors.GREEN}📝 FULL AI-GENERATED ANSWER:{Colors.ENDC}")
                    print(f"{Colors.BOLD}{'-' * 96}{Colors.ENDC}")
                    print(answer)
                    print(f"{Colors.BOLD}{'-' * 96}{Colors.ENDC}\n")
                    
                    # Display sources/citations if available
                    if sources:
                        print(f"{Colors.BOLD}{Colors.CYAN}📚 SOURCES/CITATIONS:{Colors.ENDC}")
                        for i, source in enumerate(sources, 1):
                            if isinstance(source, dict):
                                content = source.get("content", source.get("text", str(source)))[:200]
                                metadata = source.get("metadata", {})
                                print(f"  {i}. {content}...")
                                if metadata:
                                    print(f"     [Source: {metadata}]")
                            else:
                                print(f"  {i}. {str(source)[:200]}...")
                        print()
                    
                    query_result = {
                        "query_id": query_id,
                        "query_text": query_text,
                        "language": language,
                        "response": {
                            "intent": intent,
                            "score": score,
                            "tokens_generated": tokens,
                            "full_answer": answer,
                            "sources": sources,
                            "events": response.get("events", [])
                        },
                        "success": True,
                    }
                
                query_results.append(query_result)
                time.sleep(1)  # Delay between queries
            
            print(f"\n{Colors.BOLD}{Colors.YELLOW}└─ Scenario {scenario_id} complete{Colors.ENDC}")
            
            scenario_results.append({
                "scenario_id": scenario_id,
                "scenario_name": scenario_name,
                "queries": query_results
            })
        
        self.results["scenarios"] = scenario_results
        
        # Save results
        self.save_results()
    
    def save_results(self) -> None:
        """Save results to JSON file."""
        try:
            output_file = Path("legal_query_results.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(self.results, f, indent=2, ensure_ascii=False)
            
            self.print_header("TEST EXECUTION COMPLETE", char="=")
            self.print_success(f"Results saved to: {output_file.absolute()}")
            
            # Print summary
            total_queries = sum(
                len(s.get("queries", [])) 
                for s in self.results.get("scenarios", [])
            )
            successful = sum(
                1 for s in self.results.get("scenarios", [])
                for q in s.get("queries", [])
                if q.get("success", False)
            )
            
            print(f"\n{Colors.BOLD}Summary:{Colors.ENDC}")
            print(f"  Total Legal Queries: {total_queries}")
            print(f"  Successful: {successful}/{total_queries}")
            print(f"  Execution Time: {self.results.get('execution_time')}")
            print(f"  Test Type: {self.results.get('test_type')}")
            print(f"\n{Colors.GREEN}✅ All done! Check legal_query_results.json for details.{Colors.ENDC}\n")
        
        except Exception as exc:
            self.print_error(f"Failed to save results: {exc}")


def main():
    """Main entry point."""
    executor = LegalQueryExecutor()
    executor.run_test_scenarios()


if __name__ == "__main__":
    main()
