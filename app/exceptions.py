class StoreIntelligenceError(Exception):
    """Base exception for all application errors."""

class EventValidationError(StoreIntelligenceError):
    """Raised when an event fails schema validation."""

class DatabaseUnavailableError(StoreIntelligenceError):
    """Raised when the database cannot be reached."""

class CacheUnavailableError(StoreIntelligenceError):
    """Raised when Redis cannot be reached (non-fatal, fallback to DB)."""

class StoreNotFoundError(StoreIntelligenceError):
    """Raised when a store_id has no events in the system."""
