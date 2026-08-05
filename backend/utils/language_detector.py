import logging
try:
    from langdetect import detect, LangDetectException
    _LANGDETECT_AVAILABLE = True
except ImportError:
    _LANGDETECT_AVAILABLE = False
    class LangDetectException(Exception): pass

logger = logging.getLogger(__name__)


class LanguageDetector:

    @staticmethod
    def detect_language(text: str) -> str:
        """Detect language from input text using langdetect."""
        if not text or len(text.strip()) < 50 or not _LANGDETECT_AVAILABLE:
            logger.warning("Text too short or langdetect not installed — defaulting to 'english'")
            return "english"

        try:
            detected_lang = detect(text[:1000])

            if detected_lang in ("no", "nb", "nn"):
                return "norwegian"
            elif detected_lang in ("en", "en-US", "en-GB"):
                return "english"
            else:
                logger.info(f" Detected language code: {detected_lang}")
                return detected_lang
        except LangDetectException as exc:
            logger.warning(f" Language detection failed ({exc}) — defaulting to 'english'")
            return "english"
        except Exception as exc:
            logger.error(f" Language detection error ({exc}) — defaulting to 'english'")
            return "english"
