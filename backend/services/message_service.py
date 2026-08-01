import logging
import re as _re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from config import settings
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient

logger = logging.getLogger(__name__)


class MessageService:
    

    def __init__(
        self,
        supabase_client: SupabaseClient,
        redis_client: RedisClient,
        title_fetcher=None,   # LovdataTitleFetcher — optional, backward-compatible
    ) -> None:
        self._supabase      = supabase_client
        self._cache         = redis_client
        self._title_fetcher = title_fetcher
        logger.info(" MessageService initialized")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # READING MESSAGES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    def get_conversation_messages(
    self,
    conversation_id: str,
    limit: int = 100,
    offset: int = 0,
) -> List[Dict[str, Any]]:
    
        try:
            response = (
                self._supabase.table("messages")
                .select(
                    "message_id, conversation_id, role, content, "
                    "sources, metadata, created_at, type, file_name"
                )
                .eq("conversation_id", conversation_id)
                .or_("is_deleted.is.null,is_deleted.eq.false")
                .order("created_at", desc=False)
                .range(offset, offset + limit - 1)
                .execute()
            )
            messages = response.data or []

            import re
            think_re = re.compile(r'<think>.*?</think>', flags=re.DOTALL)
            source_re1 = re.compile(r'(?:^|\n)(?:Source|Kilde):\s*[^\n]+', flags=re.MULTILINE)
            source_re2 = re.compile(r'[\[\(](?:Source|Kilde):.*?[\]\)]', flags=re.DOTALL)
            newlines_re = re.compile(r'\n{3,}')

            for msg in messages:
                if msg["role"] == "assistant":
                    msg["sources"] = self._normalize_sources(msg.get("sources") or [])
                    
                    # 🔥 PHASE 1: Strip inline source citations and <think> tags
                    if msg.get("content"):
                        # Strip <think> tags
                        msg["content"] = think_re.sub('', msg["content"]).strip()
                        
                        # Strip inline source citations (both English and Norwegian)
                        # Pattern 1: "Source: ..." or "Kilde: ..." at line start or after newline
                        msg["content"] = source_re1.sub('', msg["content"]).strip()
                        
                        # Pattern 2: [Source: ...] or (Source: ...) or [Kilde: ...] or (Kilde: ...)
                        msg["content"] = source_re2.sub('', msg["content"]).strip()
                        
                        # Clean up multiple consecutive newlines left after stripping
                        msg["content"] = newlines_re.sub('\n\n', msg["content"])
                else:
                    msg["sources"] = []

                # Ensure type and file_name are always present for frontend
                msg["type"]      = msg.get("type") or "text"
                msg["file_name"] = msg.get("file_name")

            return messages

        except Exception as exc:
            logger.error(f"get_conversation_messages failed | {exc}")
            return []
            
    def get_llm_context(
        self,
        conversation_id: str,
        limit: int = 10,
    ) -> List[Dict[str, str]]:
        
        messages = self.get_conversation_messages(
            conversation_id=conversation_id,
            limit=limit,
        )
        context = [
            {"role": m["role"], "content": m["content"]}
            for m in messages
            if m["role"] in ("user", "assistant")
        ]
        logger.info(
            f" LLM context loaded | conversation={conversation_id} | messages={len(context)}"
        )
        return context

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # SAVING MESSAGES
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def save_exchange(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        metadata: Dict[str, Any],
        rag_chunks: Optional[List[Dict[str, Any]]] = None,
        skip_save_user: bool = False,
    ) -> Tuple[Optional[str], str, Dict[str, str]]:
        """
        Returns (user_msg_id, assistant_msg_id, title_map)
        title_map: {url -> resolved_title} for all source URLs in this exchange.
        chat.py uses title_map directly in Step 5 — no second fetch needed.
        """
        rag_chunks = rag_chunks or []

        try:
            # 1. Save user message
            user_msg_id = None
            if not skip_save_user:
                user_msg_id = await self._save_single_message(
                    conversation_id=conversation_id,
                    role="user",
                    content=user_message,
                )

            # 2. Resolve human-readable titles for all source URLs.
            # WHY: Milvus chunks have no doc_title field.  We fetch the title
            # from the Lovdata page (L3 httpx) and cache it in Redis (L1) and
            # Supabase lovdata_url_titles (L2).  The resolved title_map is
            # returned to chat.py so Step 5 can use it immediately for the
            # WebSocket 'complete' event — no second fetch, no timing race.
            source_urls = list(dict.fromkeys(
                chunk.get("url") or chunk.get("source_doc_url")
                for chunk in rag_chunks
                if chunk.get("url") or chunk.get("source_doc_url")
            ))
            title_map: Dict[str, str] = {}
            if source_urls and self._title_fetcher is not None:
                try:
                    title_map = await self._title_fetcher.resolve_titles(source_urls)
                except Exception as tf_exc:
                    logger.warning(f"Title resolution failed (non-fatal) | {tf_exc}")

            normalized_sources = []
            for chunk in rag_chunks:
                url = chunk.get("url") or chunk.get("source_doc_url")
                if not url:
                    continue
                title = title_map.get(url) or chunk.get("file_name") or url
                normalized_sources.append({
                    "title": title,
                    "url":   url,
                    "score": chunk.get("score"),
                })
                # Attach for save_rag_retrievals source_title column
                chunk["_resolved_title"] = title

            # 3. Save assistant message
            assistant_msg_id = await self._save_single_message(
                conversation_id=conversation_id,
                role="assistant",
                content=assistant_message,
                sources=normalized_sources,
                metadata=metadata,
            )

            # 4. Save generation metadata and RAG provenance in background thread
            import asyncio
            def _save_metadata():
                self._supabase.save_message_metadata(
                    message_id=assistant_msg_id,
                    model_name=metadata.get("model", settings.AZURE_OPENAI_DEPLOYMENT),
                    token_input=metadata.get("token_input", 0),
                    token_output=metadata.get("tokens_generated", 0),
                    latency_ms=int(metadata.get("query_time", 0) * 1000),
                    is_cached=metadata.get("cached", False),
                )
                if rag_chunks:
                    self._supabase.save_rag_retrievals(
                        message_id=assistant_msg_id,
                        chunks=rag_chunks,
                    )
            
            await asyncio.to_thread(_save_metadata)

            logger.info(
                f" Exchange saved | user={user_msg_id} | assistant={assistant_msg_id}"
            )
            return user_msg_id, assistant_msg_id, title_map

        except Exception as exc:
            logger.error(f" save_exchange failed | {exc}", exc_info=True)
            raise

    # Keep the old method name as an alias so existing callers don't break
    async def save_user_and_assistant_messages(
        self,
        conversation_id: str,
        user_message: str,
        assistant_message: str,
        metadata: Dict[str, Any],
        rag_chunks: Optional[List[Dict[str, Any]]] = None,
        skip_save_user: bool = False,
    ) -> Tuple[Optional[str], str]:
        """Alias for save_exchange() — preserved for backward compatibility."""
        return await self.save_exchange(
            conversation_id=conversation_id,
            user_message=user_message,
            assistant_message=assistant_message,
            metadata=metadata,
            rag_chunks=rag_chunks,
            skip_save_user=skip_save_user,
        )

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # INTERNAL
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

    async def _save_single_message(
        self,
        conversation_id: str,
        role: str,
        content: str,
        sources: Optional[List[Dict[str, Any]]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> str:
        
        def _sync_work():
            msg_id = self._supabase.save_message(
                conversation_id=conversation_id,
                role=role,
                content=content,
                sources=sources,
                metadata=metadata,
            )

            # Keep Redis context current
            self._cache.append_message_to_context(
                conversation_id=conversation_id,
                role=role,
                content=content,
                timestamp=datetime.utcnow(),
            )
            self._cache.extend_context_ttl(conversation_id)
            return msg_id

        import asyncio
        return await asyncio.to_thread(_sync_work)

    # ── Title translation ─────────────────────────────────────────────────────
    # WHY THIS METHOD EXISTS:
    # Lovdata documents have Norwegian titles (korttittel) like
    # "Forsikringsavtaleforskriften" or "Tvangsfullbyrdelsesloven".
    # The response is shown in English, so showing raw Norwegian titles in the
    # Sources panel is confusing.  We do a lightweight pattern-based translation
    # here — no extra API call, no latency — that handles the most common
    # Lovdata suffix patterns.  Unknown titles are passed through unchanged
    # (still better than showing a raw URL).
    @staticmethod
    def _translate_title(title: str) -> str:
        """
        Translate common Norwegian legal title suffixes to English.
        Works purely with string replacement — zero latency, no API calls.
        Titles that do not match any pattern are returned unchanged.
        """
        if not title or not title.strip():
            return title

        t = title.strip()

        # ── Full known titles ──────────────────────────────────────────────
        _KNOWN: Dict[str, str] = {
            "forsikringsavtaleforskriften": "Insurance Agreement Regulation",
            "forsikringsavtaleloven": "Insurance Agreements Act",
            "tvangsfullbyrdelsesloven": "Enforcement Act",
            "avtaleloven": "Contracts Act",
            "arbeidsmiljøloven": "Working Environment Act",
            "folketrygdloven": "National Insurance Act",
            "markedsføringsloven": "Marketing Control Act",
            "finansavtaleloven": "Financial Agreements Act",
            "verdipapirhandelloven": "Securities Trading Act",
            "panteloven": "Mortgage Act",
            "gjeldsordningsloven": "Debt Settlement Act",
            "inkassoloven": "Debt Collection Act",
            "personopplysningsloven": "Personal Data Act",
            "produktansvarsloven": "Product Liability Act",
            "kjøpsloven": "Sale of Goods Act",
            "forbrukerkjøpsloven": "Consumer Purchases Act",
            "husleieloven": "Tenancy Act",
            "burettslagslova": "Housing Cooperative Act",
            "eierseksjonsloven": "Condominium Act",
            "tinglysingsloven": "Land Registration Act",
            "skatteloven": "Tax Act",
            "merverdiavgiftsloven": "Value Added Tax Act",
            "konkursloven": "Bankruptcy Act",
            "aksjeloven": "Private Limited Companies Act",
            "allmennaksjeloven": "Public Limited Companies Act",
            "selskapslovene": "Partnership Acts",
            "straffeloven": "Penal Code",
            "straffeprosessloven": "Criminal Procedure Act",
            "tvisteloven": "Dispute Act",
            "domstolloven": "Courts of Justice Act",
            "forvaltningsloven": "Public Administration Act",
            "offentleglova": "Freedom of Information Act",
        }
        lower = t.lower()
        if lower in _KNOWN:
            return _KNOWN[lower]

        # ── Suffix-based patterns ──────────────────────────────────────────
        # Norwegian legal naming conventions:
        #   -loven       → Act / -en loven → the ... Act
        #   -forskriften → Regulation
        #   -forskrift   → Regulation
        #   -loven om    → Act on ...
        _SUFFIX_MAP = [
            ("forskriften",  "Regulation"),
            ("forskrift",    "Regulation"),
            ("loven",        "Act"),
            ("lov",          "Act"),
            ("direktivet",   "Directive"),
            ("forordningen", "Regulation (EU)"),
            ("avtalen",      "Agreement"),
        ]
        for suffix, eng_suffix in _SUFFIX_MAP:
            if lower.endswith(suffix):
                # Strip suffix, capitalise root, append English suffix
                root = t[: -len(suffix)].strip(" -")
                if root:
                    return f"{root.capitalize()} {eng_suffix}"
                return eng_suffix

        # ── Prefix-based patterns ("Forskrift om ...") ────────────────────
        _PREFIX_MAP = [
            ("forskrift om ",  "Regulation on "),
            ("lov om ",        "Act on "),
            ("forskrift til ", "Regulation to "),
        ]
        for prefix, eng_prefix in _PREFIX_MAP:
            if lower.startswith(prefix):
                rest = t[len(prefix):]
                return f"{eng_prefix}{rest}"

        # Unknown title — return as-is (better than raw URL)
        return t

    @staticmethod
    def _normalize_sources(raw: List[Any]) -> List[Dict[str, Any]]:
        """
        Normalize sources for frontend display.

        WHY THIS CHANGE:
        ─────────────────────────────────────────────────────────────────────
        Previously raw sources were emitted as plain URL strings by
        rag_service.py, so _normalize_sources had nothing to show but the URL.

        Now rag_service.py emits each source as a dict:
            {"url": "https://lovdata.no/...", "doc_title": "Forsikringsavtaleforskriften"}

        This method:
        1. Handles BOTH old (plain string) and new (dict) formats for
           backward-compatibility with messages already saved in Supabase.
        2. Picks the best available title (doc_title → title → url fallback).
        3. Translates Norwegian titles to English using the LLM if needed
           (translation is done at save time in save_exchange; here we just
           use what is stored).
        """
        normalized = []
        seen_urls: set = set()

        for item in raw:
            # ── Handle OLD format: plain URL string saved before this fix ──
            if isinstance(item, str):
                url = item.strip()
                if url and url not in seen_urls:
                    seen_urls.add(url)
                    normalized.append({"title": url, "url": url})
                continue

            if not isinstance(item, dict):
                continue

            url = item.get("url") or item.get("source_doc_url") or ""
            if not url:
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)

            # ── Pick best title (doc_title is korttittel from Lovdata XML) ──
            title = (
                item.get("title")           # already translated + stored by save_exchange
                or item.get("doc_title")    # raw Norwegian from chunk (new sources event)
                or item.get("file_name")
                or url                       # last resort: show URL
            )

            normalized.append({"title": title, "url": url})

        return normalized

    def get_title_fetcher(self):
        """Returns title_fetcher instance."""
        return self._title_fetcher

    def get_cache(self):
        """Returns redis_client cache instance."""
        return self._cache

    def get_first_messages(self, conversation_id: str, limit: int = 10) -> List[Dict[str, Any]]:
        """Fetches first N messages in chronological order for title generation."""
        try:
            resp = (
                self._supabase.table("messages")
                .select("role, content")
                .eq("conversation_id", conversation_id)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            return resp.data or []
        except Exception as exc:
            logger.warning(f"⚠️ get_first_messages failed | conv={conversation_id} | {exc}")
            return []

    def update_message_sources(self, message_id: str, sources: List[Dict[str, Any]]) -> bool:
        """Updates translated sources for a message in database."""
        try:
            resp = (
                self._supabase.table("messages")
                .update({"sources": sources})
                .eq("message_id", message_id)
                .execute()
            )
            return bool(resp.data)
        except Exception as exc:
            logger.warning(f"⚠️ update_message_sources failed | msg={message_id} | {exc}")
            return False