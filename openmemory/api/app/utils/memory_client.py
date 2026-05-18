"""
Memory client utilities for reusable memory operations.

This module provides reusable functions for common memory operations like search,
extracted from the MCP server to allow usage across different parts of the application.
"""

import logging
import uuid
from typing import Any, Dict, List, Optional, Union
from sqlalchemy.orm import Session
from qdrant_client import models as qdrant_models

from app.database import SessionLocal
from app.models import Memory, MemoryAccessLog
from app.utils.db import get_user_and_app
from app.utils.memory import get_memory_client
from opentelemetry import trace
from opentelemetry.trace import SpanKind, Status, StatusCode

_TRACER = trace.get_tracer("mem0.api.memory_client")


def _record_exception(span, exc: Exception) -> None:
    try:
        span.record_exception(exc)
        span.set_status(Status(StatusCode.ERROR, str(exc)))
    except Exception:
        # best-effort
        pass


def get_memory_client_safe():
    """Get memory client with error handling. Returns None if client cannot be initialized."""
    try:
        return get_memory_client()
    except Exception as e:
        logging.warning(f"Failed to get memory client: {e}")
        return None


async def search_memories(
    query: str,
    user_id: str,
    app_id: str,
    numberOfHits: int = 10,
    page: int = 1,
    filters: Optional[Union[qdrant_models.Filter, Dict[str, Any]]] = None
) -> List[Dict[str, Any]]:
    """
    Perform a vector search through stored memories.
    
    Args:
        query: The search query string
        user_id: ID of the user performing the search
        app_id: ID of the app/client performing the search
        numberOfHits: Maximum number of results to return
        page: Page number for pagination
        filters: Optional additional filters (qdrant_models.Filter instance or dict)
        
    Returns:
        List of memory dictionaries with search results
        
    Raises:
        AssertionError: If memory client is unavailable or required parameters missing
        ValueError: If search parameters are invalid
        MemoryError: If search operation fails
    """
    # Start a top-level span for the memory search operation
    with _TRACER.start_as_current_span("memory_client.search", kind=SpanKind.INTERNAL) as span:
        # Defensive coalescence for user-provided inputs
        # pyrefly: ignore [unnecessary-type-conversion]
        user_id = "" if user_id is None else str(user_id)
        # pyrefly: ignore [unnecessary-type-conversion]
        app_id = "" if app_id is None else str(app_id)
        # pyrefly: ignore [unnecessary-type-conversion]
        query = "" if query is None else str(query)
        if not user_id:
            error = AssertionError("Error: user_id not provided")
            _record_exception(span, error)
            raise error
        if not app_id:
            error = AssertionError("Error: app_id not provided")
            _record_exception(span, error)
            raise error

        span.set_attribute("mem0.user_id", user_id)
        span.set_attribute("mem0.app_id", app_id)
        span.set_attribute("mem0.query", query)

        # Normalize pagination inputs to avoid downstream type errors when callers pass strings
        try:
            # pyrefly: ignore [unnecessary-type-conversion]
            limit = int(numberOfHits)
        except (TypeError, ValueError):
            limit = 10
        limit = max(1, limit)

        try:
            # pyrefly: ignore [unnecessary-type-conversion]
            page_number = int(page)
        except (TypeError, ValueError):
            page_number = 1
        page_number = max(1, page_number)

        span.set_attribute("mem0.search.limit", limit)
        span.set_attribute("mem0.search.page", page_number)

        # Get memory client safely
        memory_client = get_memory_client_safe()
        if not memory_client:
            error = AssertionError("Error: Memory system is currently unavailable. Please try again later.")
            _record_exception(span, error)
            raise error

        try:
            db = SessionLocal()
            try:
                # Get or create user and app
                with _TRACER.start_as_current_span("db.get_user_and_app"):
                    user, app = get_user_and_app(db, user_id=user_id, app_id=app_id)

                # Get accessible memory IDs based on ACL
                with _TRACER.start_as_current_span("db.fetch_user_memories"):
                    user_memories = db.query(Memory).filter(Memory.user_id == user.id).all()
                    from app.utils.permissions import get_accessible_memory_ids

                    if app.is_active:
                        app_uuid = uuid.UUID(str(app.id))
                        accessible_memory_id_set = get_accessible_memory_ids(db, app_uuid, user)
                        if accessible_memory_id_set is None:
                            accessible_memory_ids = [memory.id for memory in user_memories]
                        else:
                            accessible_memory_ids = [
                                memory.id
                                for memory in user_memories
                                if memory.id in accessible_memory_id_set
                            ]
                    else:
                        accessible_memory_ids = []

                # Build baseline conditions
                conditions = [qdrant_models.FieldCondition(key="user_id", match=qdrant_models.MatchValue(value=user_id))]

                if accessible_memory_ids:
                    # Convert UUIDs to strings for Qdrant
                    accessible_memory_ids_str = [str(memory_id) for memory_id in accessible_memory_ids]
                    # pyrefly: ignore [bad-argument-type]
                    conditions.append(qdrant_models.HasIdCondition(has_id=accessible_memory_ids_str))

                # Create baseline filter
                baseline_filters = qdrant_models.Filter(must=conditions)

                # Merge with additional filters if provided
                if filters is not None and not isinstance(filters, (qdrant_models.Filter, dict)):
                    raise ValueError("filters must be a qdrant Filter or dict")

                final_filters = _merge_filters(baseline_filters, filters)
                span.set_attribute("mem0.filters_present", bool(final_filters and final_filters.must))

                # Generate embeddings (child span)
                with _TRACER.start_as_current_span("vector_store.embed") as embed_span:
                    try:
                        embeddings = memory_client.embedding_model.embed(query, "search")
                    except Exception as e:
                        _record_exception(embed_span, e)
                        raise

                # Perform the provider-level search inside its own span
                with _TRACER.start_as_current_span("vector_store.search") as vs_span:
                    try:
                        vs_span.set_attribute(
                            "mem0.vector_provider",
                            getattr(memory_client.vector_store, "__class__", type(memory_client.vector_store)).__name__,
                        )
                        vs_span.set_attribute("mem0.search.limit", limit)
                        vs_span.set_attribute("mem0.search.page", page_number)
                        vs_span.set_attribute("mem0.search.query_present", bool(query))

                        hits = memory_client.vector_store.search(
                            query,
                            embeddings,
                            limit,
                            final_filters,
                            page_number,
                        )
                    except Exception as e:
                        _record_exception(vs_span, e)
                        raise

                # Process search results
                memories = hits
                memories = [
                    {
                        "id": memory.id,
                        "memory": memory.payload.get("data") if hasattr(memory, 'payload') else getattr(memory, 'data', None),
                        "hash": (memory.payload.get("hash") if hasattr(memory, 'payload') else None),
                        "created_at": (memory.payload.get("created_at") if hasattr(memory, 'payload') else None),
                        "updated_at": (memory.payload.get("updated_at") if hasattr(memory, 'payload') else None),
                        "score": getattr(memory, 'score', None),
                    }
                    for memory in memories
                ]

                span.set_attribute("mem0.search.results_count", len(memories))

                return memories
            finally:
                db.close()
        except AssertionError as e:
            _record_exception(span, e)
            logging.exception(f"Error searching memory: {e}")
            raise e
        except ValueError as e:
            _record_exception(span, e)
            logging.exception(f"Error searching memory: {e}")
            raise ValueError(f"Error searching memory: {e}")
        except Exception as e:
            _record_exception(span, e)
            logging.exception(e)
            raise MemoryError(f"Error searching memory: {e}")


async def log_memory_access(
    memories: Union[List[Dict[str, Any]], Dict[str, Any], None],
    user_id: str,
    app_id: str,
    query: str,
    access_type: str = "search"
) -> None:
    """
    Log memory access for a list of memories.
    
    Args:
        memories: Memory search results - can be a list of dicts, a dict with 'results' key, or None
        user_id: ID of the user accessing memories
        app_id: ID of the app/client accessing memories
        query: The search query that was performed
        access_type: Type of access (default: "search")
    """
    try:
        # Defensive coalescence for caller inputs
        # pyrefly: ignore [unnecessary-type-conversion]
        user_id = "" if user_id is None else str(user_id)
        # pyrefly: ignore [unnecessary-type-conversion]
        app_id = "" if app_id is None else str(app_id)
        # pyrefly: ignore [unnecessary-type-conversion]
        query = "" if query is None else str(query)
        # pyrefly: ignore [unnecessary-type-conversion]
        access_type = "search" if access_type is None else str(access_type) or "search"

        if memories is None:
            memories = []

        db = SessionLocal()
        try:
            # Get or create user and app
            user, app = get_user_and_app(db, user_id=user_id, app_id=app_id)

            # Normalize memories into iterable of dicts
            if isinstance(memories, dict) and 'results' in memories:
                iterable = memories['results'] or []
            else:
                iterable = memories

            for memory in iterable:
                memory_id_raw = None
                if isinstance(memory, dict):
                    memory_id_raw = memory.get('id')
                    score = memory.get('score')
                    hash_val = memory.get('hash')
                else:
                    memory_id_raw = getattr(memory, 'id', None)
                    score = getattr(memory, 'score', None)
                    hash_val = getattr(memory, 'hash', None)

                if not memory_id_raw:
                    continue

                try:
                    memory_id = uuid.UUID(str(memory_id_raw))
                except Exception:
                    logging.warning("Skipping memory access log due to invalid id: %s", memory_id_raw)
                    continue

                access_log = MemoryAccessLog(
                    memory_id=memory_id,
                    app_id=app.id,
                    access_type=access_type,
                    metadata_={
                        "query": query,
                        "score": score,
                        "hash": hash_val,
                    },
                )
                db.add(access_log)

            db.commit()
        finally:
            db.close()
    except Exception as e:
        logging.exception(f"Error logging memory access: {e}")
        # Don't raise here as this is just logging


def _merge_filters(
    baseline_filters: qdrant_models.Filter,
    additional_filters: Optional[Union[qdrant_models.Filter, Dict[str, Any]]]
) -> qdrant_models.Filter:
    """
    Merge baseline filters with additional filters.
    
    Args:
        baseline_filters: The baseline Filter object with user_id and access controls
        additional_filters: Additional filters to merge (Filter instance or dict)
        
    Returns:
        Combined Filter object
    """
    if additional_filters is None:
        return baseline_filters
    
    # Convert dict to Filter if needed
    if isinstance(additional_filters, dict):
        additional_filters = qdrant_models.Filter(**additional_filters)
    
    # Combine the filters by merging their must conditions
    combined_must = []
    
    # Add baseline conditions
    if baseline_filters.must:
        combined_must.extend(baseline_filters.must)
    
    # Add additional must conditions
    if additional_filters.must:
        combined_must.extend(additional_filters.must)
    
    # For now, we'll combine must conditions and keep other conditions from additional filters
    # This could be expanded to handle more complex merging logic if needed
    return qdrant_models.Filter(
        must=combined_must if combined_must else None,
        must_not=additional_filters.must_not,
        should=additional_filters.should,
        min_should=additional_filters.min_should
    )