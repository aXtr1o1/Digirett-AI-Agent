import time
import uuid
import logging

from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from backend.config import settings
from backend.models import ChatRequest

logger = logging.getLogger(__name__)

router = APIRouter()
limiter = Limiter(key_func=get_remote_address)


@router.post("/chat/stream")
@limiter.limit(f"{settings.RATE_LIMIT_PER_MINUTE}/minute")
async def chat_stream(request: Request, body: ChatRequest):
    cid = f"req_{uuid.uuid4().hex[:8]}"
    app = request.app
    t0 = time.time()

    top_k = max(1, min(int(body.top_k), int(settings.MAX_TOP_K)))

    # normalize / clamp temp (avoid cache poison on tiny float diffs)
    temperature = float(body.temperature)
    temperature = max(0.0, min(temperature, 2.0))
    temperature_key = round(temperature, 2)

    logger.info(f"[{cid}] /chat/stream start q_len={len(body.query)} top_k={top_k} temp={temperature_key}")

    # cache key MUST include all response-shaping inputs
    cache_key = app.state.cache.generate_key(
        query=body.query,
        top_k=top_k,
        prompt_version=settings.PROMPT_VERSION,
        collection=settings.MILVUS_COLLECTION,
        embed_deployment=settings.AZURE_OPENAI_EMBEDDING_DEPLOYMENT,
        chat_deployment=settings.AZURE_OPENAI_CHAT_DEPLOYMENT,
        include_sources=bool(body.include_sources),
        temperature=temperature_key,
    )

    async def event_gen():
        async for evt in app.state.chat_service.stream(
            query=body.query,
            retriever_fn=lambda emb: app.state.retriever.search(emb, top_k, cid),
            embedder_fn=app.state.embedder.embed_query,
            cache_get_fn=app.state.cache.get if settings.ENABLE_CACHE else (lambda k: None),
            cache_set_fn=(lambda k, v: app.state.cache.set(k, v, settings.CACHE_TTL)) if settings.ENABLE_CACHE else (lambda k, v: None),
            cache_key=cache_key,
            top_k=top_k,
            include_sources=bool(body.include_sources),
            temperature=temperature,
            correlation_id=cid,
            request=request,
        ):
            yield evt

        logger.info(f"[{cid}] /chat/stream done secs={round(time.time()-t0, 4)}")

    return StreamingResponse(
        event_gen(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive", "X-Correlation-ID": cid},
    )
