import logging
from typing import Dict, Any

import httpx
from fastapi import FastAPI

from config import settings
from db.milvus_client import MilvusClient
from db.redis_client import RedisClient
from db.supabase_client import SupabaseClient
from services.billing_service import BillingService
from services.cal_service import CalService
from services.chat_orchestrator import ChatOrchestrator
from services.conversation_service import ConversationService
from services.document_service import DocumentService
from services.embedding_service import EmbeddingService
from services.email_service import EmailService
from services.hitl_service import HitlService
from services.invite_service import InviteService
from services.library_service import LibraryService
from services.llm_service import LLMService
from services.lovdata_title_fetcher import LovdataTitleFetcher
from services.message_service import MessageService
from services.notes_service import NotesService
from services.notification_service import NotificationService
from services.rag_service import RAGService
from services.rating_service import RatingService
from services.stripe_gateway import StripeGateway
from services.subscription_service import SubscriptionService
from services.ticket_message_service import TicketMessageService
from services.title_translation_service import TitleTranslationService
from services.user_service import UserService
from services.webhook_service import WebhookService

logger = logging.getLogger(__name__)


def validate_external_services_config() -> None:
    # 1. Azure OpenAI Validation
    if getattr(settings, "AZURE_OPENAI_ENDPOINT", None) and getattr(settings, "AZURE_OPENAI_API_KEY", None):
        logger.info(" Azure OpenAI configuration validated")
    else:
        logger.warning(" Azure OpenAI configuration incomplete")

    # 2. SMTP Validation
    if getattr(settings, "SMTP_HOST", None) and getattr(settings, "SMTP_USER", None):
        logger.info(f" SMTP email service configured | host={settings.SMTP_HOST}:{settings.SMTP_PORT}")
    else:
        logger.info(" SMTP email service unconfigured (fallback to log mode)")

    # 3. Clerk Validation
    if getattr(settings, "CLERK_SECRET_KEY", None):
        logger.info(" Clerk API key configured")
    else:
        logger.warning(" Clerk secret key unconfigured")

    # 4. Cal.com Validation
    if getattr(settings, "CALCOM_API_KEY", None):
        logger.info(" Cal.com API key configured")
    else:
        logger.info(" Cal.com API key unconfigured")


def init_and_register_services(
    app: FastAPI,
    milvus_client: MilvusClient,
    redis_client: RedisClient,
    supabase_client: SupabaseClient,
) -> Dict[str, Any]:
    """
    Instantiate core application services and register them onto FastAPI app.state.
    Centralized service registry without requiring third-party containers.
    """
    validate_external_services_config()

    logger.info("Initializing LLM service...")
    llm_service = LLMService(temperature=settings.OPENAI_TEMPERATURE)

    logger.info("Initializing Embedding service...")
    embedding_service = EmbeddingService()

    logger.info("Initializing Document service...")
    document_service = DocumentService(
        redis_client=redis_client,
        supabase_client=supabase_client,
    )

    logger.info("Initializing RAG service...")
    rag_service = RAGService(
        llm_service=llm_service,
        milvus_client=milvus_client,
        redis_client=redis_client,
        supabase_client=supabase_client,
        embedding_service=embedding_service,
        document_service=document_service,
    )

    logger.info("Initializing Conversation service...")
    conversation_service = ConversationService(
        supabase_client=supabase_client,
        redis_client=redis_client,
    )

    logger.info("Initializing User service...")
    user_service = UserService(
        supabase_client=supabase_client,
    )

    logger.info("Initializing Hitl service...")
    hitl_service = HitlService(
        supabase_client=supabase_client,
    )

    logger.info("Initializing Email service...")
    email_service = EmailService(
        smtp_host=settings.SMTP_HOST,
        smtp_port=settings.SMTP_PORT,
        smtp_user=settings.SMTP_USER,
        smtp_pass=settings.SMTP_PASS,
        from_email=settings.INVITE_FROM_EMAIL,
    )

    logger.info("Initializing Cal service...")
    cal_service = CalService()

    logger.info("Initializing LovdataTitleFetcher service...")
    lovdata_title_fetcher = LovdataTitleFetcher(
        redis_client=redis_client,
        supabase_client=supabase_client,
    )

    logger.info("Initializing Message service...")
    message_service = MessageService(
        supabase_client=supabase_client,
        redis_client=redis_client,
        title_fetcher=lovdata_title_fetcher,
    )

    logger.info("Initializing Notes service...")
    notes_service = NotesService(
        supabase_client=supabase_client,
    )

    logger.info("Initializing Library service...")
    library_service = LibraryService(
        supabase_client=supabase_client,
    )

    stripe_gateway = StripeGateway(api_key=getattr(settings, "STRIPE_SECRET_KEY", ""))
    billing_service = BillingService(
        stripe_gateway=stripe_gateway,
        user_service=user_service,
    )

    invite_service = InviteService(
        supabase_client=supabase_client,
    )

    notification_service = NotificationService(
        email_service=email_service,
        supabase_client=supabase_client,
    )

    rating_service = RatingService(
        supabase_client=supabase_client,
        notification_service=notification_service,
    )

    subscription_service = SubscriptionService(
        user_service=user_service,
        supabase_client=supabase_client,
    )

    ticket_message_service = TicketMessageService(
        supabase_client=supabase_client,
        notification_service=notification_service,
    )

    title_translation_service = TitleTranslationService(
        llm_service=llm_service,
        message_service=message_service,
    )

    webhook_service = WebhookService(
        user_service=user_service,
        subscription_service=subscription_service,
        email_service=email_service,
    )

    chat_orchestrator = ChatOrchestrator(
        rag_service=rag_service,
        conversation_service=conversation_service,
        message_service=message_service,
        llm_service=llm_service,
        document_service=document_service,
        user_service=user_service,
        title_translation_service=title_translation_service,
    )

    # Attach all services to app.state
    app.state.llm_service = llm_service
    app.state.embedding_service = embedding_service
    app.state.document_service = document_service
    app.state.rag_service = rag_service
    app.state.conversation_service = conversation_service
    app.state.user_service = user_service
    app.state.hitl_service = hitl_service
    app.state.email_service = email_service
    app.state.cal_service = cal_service
    app.state.message_service = message_service
    app.state.notes_service = notes_service
    app.state.library_service = library_service
    app.state.billing_service = billing_service
    app.state.invite_service = invite_service
    app.state.notification_service = notification_service
    app.state.rating_service = rating_service
    app.state.subscription_service = subscription_service
    app.state.ticket_message_service = ticket_message_service
    app.state.title_translation_service = title_translation_service
    app.state.webhook_service = webhook_service
    app.state.chat_orchestrator = chat_orchestrator

    logger.info("[OK] All application services registered onto app.state")
    return app.state.__dict__
