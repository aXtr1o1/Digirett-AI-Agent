import logging

from fastapi import APIRouter, HTTPException, status

from schemas.responses import HealthResponse

logger = logging.getLogger(__name__)
router = APIRouter()

# Injected from main.py via set_services()
_milvus = None
_redis = None
_supabase = None
_llm = None


def set_clients(milvus, redis, supabase, llm) -> None:
    global _milvus, _redis, _supabase, _llm
    _milvus = milvus
    _redis = redis
    _supabase = supabase
    _llm = llm


@router.get(
    "/health",
    response_model=HealthResponse,
    tags=["System"],
    summary="System health check",
)
async def health_check():

    try:
        milvus_ok  = _milvus.check_connection()  if _milvus   else False
        redis_ok   = _redis.check_connection()   if _redis    else False
        supabase_ok = _supabase.check_connection() if _supabase else False
        llm_ok     = await _llm.check_connection() if _llm     else False

        all_healthy = all([milvus_ok, redis_ok, supabase_ok, llm_ok])

        return HealthResponse(
            status="healthy" if all_healthy else "degraded",
            version="2.0.0",
            milvus_connected=milvus_ok,
            cache_connected=redis_ok,
            supabase_connected=supabase_ok,
            llm_connected=llm_ok,
        )

    except Exception as exc:
        logger.error(f" Health check failed | {exc}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Health check failed: {exc}",
        )