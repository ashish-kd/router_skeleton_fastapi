import os
import json
import time
import random
import string
import asyncio
import statistics
import argparse
from typing import List, Dict, Any, Optional
import aiohttp
from aiohttp import ClientSession
import numpy as np
from rich.console import Console
from rich.progress import Progress, TextColumn, BarColumn, TimeElapsedColumn, TaskID

# Configuration
API_URL = os.getenv("API_URL", "http://localhost:8000/route")
API_KEY = os.getenv("API_KEY", "dev-key")
CONSOLE = Console()

# Message types for load testing
MESSAGE_TYPES = [
    {"type": "assist", "templates": [
        "Can you help me with {topic}?",
        "I need assistance with {topic}.",
        "Please explain how to {topic}."
    ]},
    {"type": "policy", "templates": [
        "What is the policy regarding {topic}?",
        "Is there a compliance requirement for {topic}?",
        "Can you check the GDPR rules for {topic}?"
    ]},
    {"type": "emergency", "templates": [
        "URGENT: Need immediate help with {topic}!",
        "This is an emergency situation about {topic}!",
        "911 situation: {topic} is failing right now!"
    ]}
]

# Random topics to make messages more varied
TOPICS = [
    "account access", "password reset", "data migration",
    "user permissions", "file corruption", "network connectivity",
    "database query", "authentication failure", "certificate expiration",
    "application performance", "memory leak", "disk space", "backup failure"
]

def generate_random_message() -> Dict[str, Any]:
    """Generate a random message for load testing using specification format"""
    # Select random message type and template
    message_type = random.choice(MESSAGE_TYPES)
    template = random.choice(message_type["templates"])
    topic = random.choice(TOPICS)
    
    # Generate message text
    message_text = template.format(topic=topic)
    
    # Add some random data to make each message unique
    rand_suffix = ''.join(random.choice(string.ascii_letters) for _ in range(8))
    
    # Generate specification-compliant request
    return {
        "tenant_id": f"tenant_{random.randint(1, 3)}",  # Multiple tenants for testing
        "user_id": f"user_{rand_suffix}",
        "payload_version": 1,
        "type": message_type["type"] + "_request", 
        "ts": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "text": message_text,
        "metadata": {
            "source": "load_test",
            "request_id": rand_suffix,
            "priority": random.choice(["normal", "high"]) if message_type["type"] == "emergency" else "normal"
        }
    }

async def send_request(
    session: ClientSession,
    sender_id: str,
    request_num: int,
    results: List[Dict[str, Any]]
) -> Dict[str, Any]:
    """Send a single request and collect metrics"""
    # Generate specification-compliant payload
    req_data = generate_random_message()
    
    # Sometimes include event_id for testing canonical message_id generation
    if random.random() < 0.3:
        req_data["event_id"] = f"evt_{random.randint(1000, 9999)}"
    
    # Sometimes override kind for testing classification override
    if random.random() < 0.1:
        req_data["kind"] = random.choice(["assist", "policy", "emergency"])
    
    start_time = time.perf_counter()
    
    try:
        async with session.post(
            API_URL,
            headers={"X-API-Key": API_KEY, "Content-Type": "application/json"},
            json=req_data,
            timeout=10
        ) as response:
            end_time = time.perf_counter()
            duration_ms = (end_time - start_time) * 1000
            
            # Parse response
            if response.status == 200:
                resp_json = await response.json()
                result = {
                    "request_num": request_num,
                    "status_code": response.status,
                    "duration_ms": duration_ms,
                    "sender_id": sender_id,
                    "trace_id": resp_json.get("trace_id", "unknown"),
                    "routed_agents": resp_json.get("routed_agents", []),
                    "success": True
                }
            else:
                result = {
                    "request_num": request_num,
                    "status_code": response.status,
                    "duration_ms": duration_ms,
                    "sender_id": sender_id,
                    "error": await response.text(),
                    "success": False
                }
            
            results.append(result)
            return result
    except Exception as e:
        end_time = time.perf_counter()
        duration_ms = (end_time - start_time) * 1000
        result = {
            "request_num": request_num,
            "status_code": 0,
            "duration_ms": duration_ms,
            "sender_id": sender_id,
            "error": str(e),
            "success": False
        }
        results.append(result)
        return result

async def run_load_test(
    num_requests: int,
    concurrency: int,
    rps_limit: Optional[int] = None,
    num_senders: int = 10
) -> List[Dict[str, Any]]:
    """Run a load test with specified parameters"""
    results = []
    
    # Create a connection pool and reuse sessions
    connector = aiohttp.TCPConnector(limit=concurrency, limit_per_host=concurrency)
    
    async with ClientSession(connector=connector) as session:
        with Progress(
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn()
        ) as progress:
            task = progress.add_task("[green]Running load test...", total=num_requests)
            
            # Create task generator
            async def task_generator():
                for i in range(num_requests):
                    # Assign a sender_id from the pool
                    sender_id = f"user_{i % num_senders}"
                    
                    # Yield the task
                    yield send_request(session, sender_id, i, results)
                    
                    # Rate limiting if specified
                    if rps_limit:
                        await asyncio.sleep(1 / rps_limit)
            
            # Use semaphore to limit concurrency
            sem = asyncio.Semaphore(concurrency)
            
            async def bounded_task(coro):
                async with sem:
                    result = await coro
                    progress.update(task, advance=1)
                    return result
            
            # Execute tasks with bounded concurrency
            tasks_iter = [bounded_task(task) async for task in task_generator()]
            await asyncio.gather(*tasks_iter)
    
    return results

def analyze_results(results: List[Dict[str, Any]]):
    """Analyze and print load test results"""
    if not results:
        CONSOLE.print("[bold red]No results collected![/]")
        return
    
    # Show first few errors for debugging
    errors = [r for r in results if not r["success"]]
    if errors:
        CONSOLE.print(f"[bold red]Found {len(errors)} errors. First few:[/]")
        for i, error in enumerate(errors[:3]):
            CONSOLE.print(f"  Error {i+1}: Status {error['status_code']}")
            if 'error' in error:
                CONSOLE.print(f"    Message: {error['error'][:200]}...")
    
    # Extract durations
    durations = [r["duration_ms"] for r in results if r["success"]]
    if not durations:
        CONSOLE.print("[bold red]No successful requests![/]")
        return
    
    # Calculate statistics
    durations.sort()
    total_count = len(results)
    success_count = len(durations)
    error_count = total_count - success_count
    error_rate = error_count / total_count * 100 if total_count > 0 else 0
    
    p50 = np.percentile(durations, 50)
    p95 = np.percentile(durations, 95)
    p99 = np.percentile(durations, 99)
    mean = statistics.mean(durations)
    
    # Print results
    CONSOLE.print("\n[bold green]===== Load Test Results =====[/]")
    CONSOLE.print(f"[bold]Total Requests:[/] {total_count}")
    CONSOLE.print(f"[bold]Successful:[/] {success_count}")
    CONSOLE.print(f"[bold]Errors:[/] {error_count} ({error_rate:.2f}%)")
    CONSOLE.print("\n[bold]Latency (ms):[/]")
    CONSOLE.print(f"  [bold]Mean:[/] {mean:.2f}")
    CONSOLE.print(f"  [bold]P50:[/] {p50:.2f}")
    CONSOLE.print(f"  [bold]P95:[/] {p95:.2f}")
    CONSOLE.print(f"  [bold]P99:[/] {p99:.2f}")
    
    # Check SLO compliance
    slo_p50 = 5.0  # 5ms
    slo_p95 = 15.0  # 15ms
    
    if p50 <= slo_p50:
        CONSOLE.print(f"[bold green]✓ P50 SLO MET[/] ({p50:.2f}ms <= {slo_p50}ms)")
    else:
        CONSOLE.print(f"[bold red]✗ P50 SLO MISSED[/] ({p50:.2f}ms > {slo_p50}ms)")
        
    if p95 <= slo_p95:
        CONSOLE.print(f"[bold green]✓ P95 SLO MET[/] ({p95:.2f}ms <= {slo_p95}ms)")
    else:
        CONSOLE.print(f"[bold red]✗ P95 SLO MISSED[/] ({p95:.2f}ms > {slo_p95}ms)")
    
    # Check for error budget
    error_budget = 0.1  # 0.1%
    if error_rate <= error_budget:
        CONSOLE.print(f"[bold green]✓ ERROR BUDGET MET[/] ({error_rate:.2f}% <= {error_budget}%)")
    else:
        CONSOLE.print(f"[bold red]✗ ERROR BUDGET EXCEEDED[/] ({error_rate:.2f}% > {error_budget}%)")

async def main():
    """Main function"""
    parser = argparse.ArgumentParser(description='Load test for the router service')
    parser.add_argument('-n', '--num-requests', type=int, default=1000,
                        help='Number of requests to send (default: 1000)')
    parser.add_argument('-c', '--concurrency', type=int, default=50,
                        help='Number of concurrent requests (default: 50)')
    parser.add_argument('-r', '--rps', type=int, default=None,
                        help='Rate limit in requests per second (default: None)')
    parser.add_argument('-s', '--senders', type=int, default=10,
                        help='Number of unique sender_ids to use (default: 10)')
    args = parser.parse_args()
    
    CONSOLE.print("[bold]Starting load test with the following parameters:[/]")
    CONSOLE.print(f"  [bold]Requests:[/] {args.num_requests}")
    CONSOLE.print(f"  [bold]Concurrency:[/] {args.concurrency}")
    CONSOLE.print(f"  [bold]RPS Limit:[/] {args.rps if args.rps else 'None'}")
    CONSOLE.print(f"  [bold]Unique Senders:[/] {args.senders}")
    CONSOLE.print(f"  [bold]Target URL:[/] {API_URL}")
    
    start_time = time.time()
    results = await run_load_test(
        args.num_requests, 
        args.concurrency,
        args.rps,
        args.senders
    )
    end_time = time.time()
    
    # Calculate overall RPS
    duration = end_time - start_time
    rps = args.num_requests / duration
    
    CONSOLE.print(f"\n[bold]Test Duration:[/] {duration:.2f}s")
    CONSOLE.print(f"[bold]Average RPS:[/] {rps:.2f}")
    
    analyze_results(results)

if __name__ == "__main__":
    asyncio.run(main())
