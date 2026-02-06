"""
terminal_chat.py
Interactive terminal interface for Lovdata RAG system
"""

import asyncio
import httpx
import json
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.prompt import Prompt
import sys

console = Console()

# Try multiple possible API URLs
API_URLS = [
    "http://127.0.0.1:8000",
    "http://localhost:8000",
    "http://0.0.0.0:8000"
]

API_BASE_URL = None


async def find_api_url():
    """Try to find the correct API URL"""
    global API_BASE_URL
    
    for url in API_URLS:
        try:
            async with httpx.AsyncClient(timeout=3.0) as client:
                response = await client.get(f"{url}/health")
                if response.status_code == 200:
                    API_BASE_URL = url
                    return True
        except:
            continue
    
    return False


async def chat_with_rag(query: str, use_streaming: bool = True):
    """Send query to RAG API and display response"""
    
    if use_streaming:
        await chat_with_streaming(query)
    else:
        await chat_with_regular(query)


async def chat_with_streaming(query: str):
    """Chat with streaming response (like ChatGPT)"""
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Send streaming request
            async with client.stream(
                "POST",
                f"{API_BASE_URL}/chat/stream",
                json={
                    "query": query,
                    "top_k": 3,
                    "temperature": 0.1
                }
            ) as response:
                
                if response.status_code != 200:
                    console.print(f"[red]Error: {response.status_code}[/red]")
                    return
                
                sources_shown = False
                answer_parts = []
                
                # Process streaming events
                async for line in response.aiter_lines():
                    if not line.strip() or not line.startswith("data: "):
                        continue
                    
                    try:
                        # Parse event data
                        data = json.loads(line[6:])  # Remove "data: " prefix
                        event_type = data.get("type")
                        
                        if event_type == "sources":
                            # Show sources first
                            sources = data.get("data", [])
                            
                            # ✅ ONLY show sources section if we actually have sources
                            if sources and len(sources) > 0:
                                if not sources_shown:
                                    console.print("\n[bold blue]📚 Sources:[/bold blue]")
                                    for i, source in enumerate(sources, 1):
                                        console.print(f"  {i}. [link]{source.get('url', 'N/A')}[/link]")
                                    console.print()
                                    sources_shown = True
                            else:
                                # Empty sources = skip showing the section entirely
                                sources_shown = True  # Mark as handled but don't display
                        
                        elif event_type == "token":
                            # Stream tokens (like ChatGPT!)
                            token = data.get("data", "")
                            if not answer_parts:
                                console.print("[bold green]Answer:[/bold green] ", end="")
                            console.print(token, end="")
                            answer_parts.append(token)
                            
                        elif event_type == "complete":
                            # If backend sent a full answer (no-stream case)
                            if "answer" in data:
                                console.print("\n[bold green]Answer:[/bold green]")
                                console.print(data["answer"])

                            metadata = data.get("metadata", {})

                            info_parts = []
                            if metadata.get("language"):
                                info_parts.append(f"Language: {metadata['language']}")
                            if metadata.get("chunks_retrieved") is not None:
                                info_parts.append(f"Chunks: {metadata.get('chunks_retrieved', 0)}")

                            if info_parts:
                                console.print(f"[dim]{' | '.join(info_parts)}[/dim]")

                            
                            # Show metadata
                            casual = metadata.get("casual_conversation", False)
                            language = metadata.get("language", "unknown")
                            chunks = metadata.get("chunks_retrieved", 0)
                            
                            info_parts = []
                            if language:
                                info_parts.append(f"Language: {language}")
                            if not casual and chunks:
                                info_parts.append(f"Chunks: {chunks}")
                            
                            if info_parts:
                                console.print(f"[dim]{' | '.join(info_parts)}[/dim]")
                        
                        elif event_type == "error":
                            console.print(f"\n[red]Error: {data.get('message')}[/red]")
                            return
                    
                    except json.JSONDecodeError:
                        continue
                
    except httpx.TimeoutException:
        console.print("[red]Request timed out. Please try again.[/red]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to API. Please check if it's running.[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


async def chat_with_regular(query: str):
    """Chat with regular response (wait for full answer)"""
    
    try:
        async with httpx.AsyncClient(timeout=60.0) as client:
            # Send query
            response = await client.post(
                f"{API_BASE_URL}/chat",
                json={
                    "query": query,
                    "top_k": 3,
                    "include_sources": True,
                    "temperature": 0.1
                }
            )
            
            if response.status_code == 200:
                data = response.json()
                
                # Display answer
                console.print("\n[bold green]Answer:[/bold green]")
                console.print(Panel(data["answer"], border_style="green"))
                
                # Display sources if available
                if data.get("sources"):
                    console.print("\n[bold blue]Sources:[/bold blue]")
                    for i, source in enumerate(data["sources"], 1):
                        console.print(f"\n{i}. [bold]{source['title']}[/bold]")
                        console.print(f"   URL: [link]{source['url']}[/link]")
                        console.print(f"   Relevance: {source['relevance_score']:.2%}")
                
                # Display metadata
                metadata = data.get("metadata", {})
                console.print(f"\n[dim]Query time: {metadata.get('query_time', 0):.2f}s | "
                            f"Chunks: {metadata.get('chunks_retrieved', 0)} | "
                            f"Cached: {metadata.get('cached', False)}[/dim]")
                
            elif response.status_code == 500:
                console.print("[red]Server error. Please check API logs.[/red]")
                try:
                    error_data = response.json()
                    if "detail" in error_data:
                        console.print(f"[dim]{error_data['detail']}[/dim]")
                except:
                    pass
            else:
                console.print(f"[red]Error: {response.status_code}[/red]")
                console.print(response.text)
                
    except httpx.TimeoutException:
        console.print("[red]Request timed out. Please try again.[/red]")
    except httpx.ConnectError:
        console.print("[red]Cannot connect to API. Please check if it's running.[/red]")
    except Exception as e:
        console.print(f"[red]Error: {e}[/red]")


async def check_api_health():
    """Check if API is running and healthy"""
    try:
        if not API_BASE_URL:
            return False
            
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.get(f"{API_BASE_URL}/health")
            if response.status_code == 200:
                data = response.json()
                
                # Display service status
                console.print(f"[green]✓ API Status: {data['status']}[/green]")
                console.print(f"[dim]  Milvus: {'✓' if data.get('milvus_connected') else '✗'}[/dim]")
                console.print(f"[dim]  LLM: {'✓' if data.get('llm_connected') else '✗'}[/dim]")
                console.print(f"[dim]  Cache: {'✓' if data.get('cache_connected') else '✗'}[/dim]")
                
                return data["status"] == "healthy"
        
        return False
        
    except Exception as e:
        console.print(f"[red]Health check failed: {e}[/red]")
        return False


async def main():
    """Main terminal chat loop"""
    
    # Display welcome banner
    console.clear()
    console.print(Panel.fit(
        "[bold cyan]Lovdata Legal Assistant[/bold cyan]\n"
        "Your AI assistant for Norwegian company laws\n\n"
        "[dim]Commands: 'exit' or 'quit' to exit[/dim]",
        border_style="cyan"
    ))
    
    # Find and connect to API
    console.print("\n[yellow]Searching for API...[/yellow]")
    
    if not await find_api_url():
        console.print("\n" + "="*60)
        console.print("[bold red]ERROR: Cannot connect to API![/bold red]")
        console.print("="*60)
        console.print("\n[yellow]Troubleshooting:[/yellow]")
        console.print("1. Check if API is running in another terminal")
        console.print("   Look for: [green]'Application startup complete'[/green]")
        console.print("\n2. If not running, start it with:")
        console.print("   [bold cyan]uvicorn app.main:app --reload[/bold cyan]")
        console.print("\n3. Verify API is accessible:")
        console.print("   [cyan]curl http://localhost:8000/health[/cyan]")
        console.print("\n4. Check these ports are available:")
        for url in API_URLS:
            console.print(f"   - {url}")
        console.print("="*60)
        sys.exit(1)
    
    console.print(f"[green]✓ Connected to: {API_BASE_URL}[/green]\n")
    
    # Check API health
    if not await check_api_health():
        console.print("\n[yellow]⚠ Warning: Some services may not be fully initialized[/yellow]")
        console.print("[dim]You can still try to use the chat, but some features may not work.[/dim]\n")
    
    console.print("\n[bold green]Ready! Start chatting...[/bold green]")
    
    # Main chat loop
    while True:
        try:
            # Get user input
            user_input = Prompt.ask("\n[bold cyan]You[/bold cyan]")
            
            # Check for exit commands
            if user_input.lower().strip() in ['exit', 'quit', 'q', 'bye']:
                console.print("\n[yellow]👋 Goodbye! Have a great day![/yellow]")
                break
            
            # Skip empty input
            if not user_input.strip():
                continue
            
            # Show processing indicator
            console.print("[dim]Thinking...[/dim]")
            
            # Process query with streaming (ChatGPT-like!)
            await chat_with_rag(query=user_input, use_streaming=True)
            
        except KeyboardInterrupt:
            console.print("\n\n[yellow]⚠ Interrupted. Type 'exit' to quit.[/yellow]")
            continue
        except EOFError:
            console.print("\n[yellow]Exiting...[/yellow]")
            break
        except Exception as e:
            console.print(f"\n[red]Unexpected error: {e}[/red]")
            console.print("[dim]Please try again or contact support.[/dim]")


if __name__ == "__main__":
    try:
        # Set event loop policy for Windows
        if sys.platform == 'win32':
            asyncio.set_event_loop_policy(asyncio.WindowsProactorEventLoopPolicy())
        
        asyncio.run(main())
        
    except KeyboardInterrupt:
        console.print("\n[yellow]Exiting...[/yellow]")
    except Exception as e:
        console.print(f"\n[red]Fatal error: {e}[/red]")
        sys.exit(1)