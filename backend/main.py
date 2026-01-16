from prometheus_client import Counter, generate_latest
from fastapi import FastAPI, Response

app = FastAPI()

REQUEST_COUNT = Counter("http_requests_total", "Total HTTP requests")

@app.middleware("http")
async def count_requests(request, call_next):
    REQUEST_COUNT.inc()
    return await call_next(request)

@app.get("/metrics")
def metrics():
    return Response(generate_latest(), media_type="text/plain")

