"""
MCP Server for OpenMemory with resilient memory client handling.

This module implements an MCP (Model Context Protocol) server that provides
memory operations for OpenMemory. The memory client is initialized lazily
to prevent server crashes when external dependencies (like Ollama) are
unavailable. If the memory client cannot be initialized, the server will
continue running with limited functionality and appropriate error messages.

Key features:
- Lazy memory client initialization
- Graceful error handling for unavailable dependencies
- Fallback to database-only mode when vector store is unavailable
- Proper logging for debugging connection issues
- Environment variable parsing for API keys
"""

import logging
import json
from typing import Any, Dict, List, Mapping, Optional, TypedDict
from mcp.server.fastmcp import FastMCP, Context
from opentelemetry import context as otel_context, trace
from opentelemetry.propagate import extract
from opentelemetry.trace import (
    SpanKind,
    Status,
    StatusCode,
    SpanContext,
    TraceFlags,
    NonRecordingSpan,
    set_span_in_context,
    TraceState,
)
import re
from mcp.server.sse import SseServerTransport
from app.utils.memory import get_memory_client
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.routing import APIRouter
import contextvars
import datetime
import json
import logging
import uuid
from typing import Any, Dict, List, Mapping, Union

from app.auth import get_user_record
from app.database import SessionLocal
from app.models import Memory, MemoryAccessLog, MemoryState, MemoryStatusHistory, User
from app.utils.db import get_user_and_app
from app.utils.memory import get_memory_client
from app.utils.memory_client import log_memory_access, search_memories
from app.utils.permissions import check_memory_access_permissions
from app.utils.telemetry import (
    _attach_trace_context_from_request,
    _detach_trace_context,
    _record_exception,
)
from dotenv import load_dotenv
from mcp.server.fastmcp import FastMCP
from mcp.server.sse import SseServerTransport
from opentelemetry import trace
from opentelemetry.trace import SpanKind
from qdrant_client import models as qdrant_models


class FilterClause(TypedDict, total=False):
    """Minimal Qdrant filter clause: either a match or a range."""
    key: str
    match: Dict[str, Any]
    range: Dict[str, Any]


class FilterDict(TypedDict, total=False):
    """Lightweight Qdrant filter structure used by search_memory."""
    must: List[FilterClause]
    must_not: List[FilterClause]
    should: List[FilterClause]

# Load environment variables
load_dotenv()

# Initialize MCP
mcp = FastMCP("mem0-mcp-server")

# Don't initialize memory client at import time - do it lazily when needed
def get_memory_client_safe():
    """Get memory client with error handling. Returns None if client cannot be initialized."""
    try:
        return get_memory_client()
    except Exception as e:
        logging.warning(f"Failed to get memory client: {e}")
        return None

# Context variables for user_id and client_name
user_id_var: contextvars.ContextVar[str] = contextvars.ContextVar("user_id")
client_name_var: contextvars.ContextVar[str] = contextvars.ContextVar("client_name")

_TRACER = trace.get_tracer("mem0.mcp")


def _attach_trace_context_from_request(request: Request) -> Optional[object]:
    """Attach OpenTelemetry context derived from incoming request headers."""
    try:
        # Prefer explicit W3C traceparent header parsing so we can set remote parent
        traceparent = request.headers.get("traceparent")
        if traceparent:
            # W3C traceparent format: 00-<trace-id>-<parent-id>-<trace-flags>
            m = re.match(r"^[ \t]*([0-9a-fA-F]{2})-([0-9a-fA-F]{32})-([0-9a-fA-F]{16})-([0-9a-fA-F]{2})", traceparent)
            if m:
                version, trace_id_hex, parent_id_hex, trace_flags_hex = m.groups()
                trace_id = int(trace_id_hex, 16)
                span_id = int(parent_id_hex, 16)
                flags = int(trace_flags_hex, 16)

                # Build a remote SpanContext as parent
                parent_span_context = SpanContext(
                    trace_id=trace_id,
                    span_id=span_id,
                    is_remote=True,
                    trace_flags=TraceFlags(flags),
                    trace_state=TraceState(),
                )
                parent_span = NonRecordingSpan(parent_span_context)
                ctx = set_span_in_context(parent_span)
                logging.debug("Attached remote parent span: trace_id=%s span_id=%s", trace_id_hex, parent_id_hex)
                return otel_context.attach(ctx)

        # Fallback to normal propagator extraction
        context = extract(request.headers)
        logging.debug("Propagator extracted context: %s", bool(context))
        return otel_context.attach(context)
    except Exception as exc:  # pragma: no cover - defensive logging
        logging.debug("Failed to extract trace context: %s", exc)
        return None

def _detach_trace_context(token: Optional[object]) -> None:
    if token is not None:
        otel_context.detach(token)


def _record_exception(span, exc: Exception) -> None:
    span.record_exception(exc)
    span.set_status(Status(StatusCode.ERROR, str(exc)))

# Create a router for MCP endpoints
mcp_router = APIRouter(prefix="/mcp")

# Initialize SSE transport
sse = SseServerTransport("/mcp/messages")

@mcp.tool(description="Add a new memory. This method is called everytime the user informs anything about themselves, their preferences, or anything that has any relevant information which can be useful in the future conversation. This can also be called when the user asks you to remember something.  " +
          "Metadata can be provided to store additional information that can be useful for filtering or categorizing memories later.  Any arbitrary metadata can be provided, but some special keys include:\n - 'document_id': The case file or document to associate with a memory.  Always provide this if available.\n - 'created_at': when present, this will be used as the memory creation date.  This should always be set to the send date of the analyzed document. - 'chat_thread': the thread ID of the chat where this message was sent.")
async def add_memories(text: str, metadata: Mapping[str, Any] = None) -> str | Mapping[str, str | List[Any] | Mapping[str, Any]]:
    metadata = dict(metadata or {})
    logging.info("Add Memory called with text: %s", text)

    with _TRACER.start_as_current_span("mcp.tool.add_memories", kind=SpanKind.INTERNAL) as span:
        uid = user_id_var.get(None)
        client_name = client_name_var.get(None)
        span.set_attribute("mem0.user_id", uid or "")
        span.set_attribute("mem0.client_name", client_name or "")
        span.set_attribute("mem0.metadata_size", len(metadata))
        span.set_attribute("mem0.text_length", len(text or ""))

        if not uid:
            error = AssertionError("Error: user_id not provided")
            _record_exception(span, error)
            raise error
        if not client_name:
            error = AssertionError("Error: client_name not provided")
            _record_exception(span, error)
            raise error

        memory_client = get_memory_client_safe()
        if not memory_client:
            error = AssertionError("Memory system is currently unavailable. Please try again later.")
            _record_exception(span, error)
            raise error

        try:
            db = SessionLocal()
            try:
                with _TRACER.start_as_current_span("db.get_user_and_app"):
                    user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

                if not app.is_active:
                    raise ValueError(f"Error: App {app.name} is currently paused on OpenMemory. Cannot create new memories.")

                default_metadata = {
                    "source_app": "openmemory",
                    "mcp_client": client_name,
                }
                meta = {**default_metadata, **metadata}
                span.set_attribute("mem0.metadata_keys", ",".join(sorted(meta.keys())))

                with _TRACER.start_as_current_span("memory_client.add") as memory_span:
                    memory_span.set_attribute("mem0.metadata_count", len(meta))
                    response = memory_client.add(
                        text,
                        user_id=uid,
                        metadata=meta,
                    )

                memory_timestamp = datetime.datetime.fromisoformat(
                    meta.pop("created_at", datetime.datetime.now(datetime.UTC).isoformat())
                )

                if isinstance(response, dict) and "results" in response:
                    with _TRACER.start_as_current_span("db.sync_results"):
                        for result in response["results"]:
                            memory_id = uuid.UUID(result["id"])
                            memory = db.query(Memory).filter(Memory.id == memory_id).first()

                            if result["event"] == "ADD":
                                if not memory:
                                    memory = Memory(
                                        id=memory_id,
                                        user_id=user.id,
                                        app_id=app.id,
                                        metadata=meta,
                                        created_at=memory_timestamp,
                                        content=result["memory"],
                                        state=MemoryState.active,
                                    )
                                    db.add(memory)
                                else:
                                    memory.state = MemoryState.active
                                    memory.content = result["memory"]

                                history = MemoryStatusHistory(
                                    memory_id=memory_id,
                                    changed_by=user.id,
                                    changed_at=memory_timestamp,
                                    old_state=MemoryState.deleted if memory else None,
                                    new_state=MemoryState.active,
                                )
                                db.add(history)

                            elif result["event"] == "DELETE":
                                if memory:
                                    memory.state = MemoryState.deleted
                                    memory.deleted_at = datetime.datetime.now(datetime.UTC)
                                    history = MemoryStatusHistory(
                                        memory_id=memory_id,
                                        changed_by=user.id,
                                        old_state=MemoryState.active,
                                        new_state=MemoryState.deleted,
                                    )
                                    db.add(history)

                    with _TRACER.start_as_current_span("db.commit"):
                        db.commit()

                else:
                    with _TRACER.start_as_current_span("db.commit"):
                        db.commit()

                return response
            finally:
                db.close()
        except AssertionError as e:
            _record_exception(span, e)
            logging.exception(f"Error adding to memory: {e}")
            raise
        except ValueError as e:
            _record_exception(span, e)
            logging.exception(f"Error adding to memory: {e}")
            raise
        except Exception as e:
            _record_exception(span, e)
            logging.exception(f"Error adding to memory: {e}")
            raise MemoryError(f"Error adding to memory: {e}")


@mcp.tool(description="Peforms a vector Search through stored memories. This method is called EVERYTIME the user asks anything.  Supports pagination if more context is necessary, but pay attention to the result score.")
async def search_memory(query: str, numberOfHits = 10, page = 1, filters: Optional[FilterDict] = None) -> str:
    logging.info("Search Memory called with query: %s", query)

    with _TRACER.start_as_current_span("mcp.tool.search_memory", kind=SpanKind.INTERNAL) as span:
        uid = user_id_var.get(None)
        client_name = client_name_var.get(None)
        span.set_attribute("mem0.user_id", uid or "")
        span.set_attribute("mem0.client_name", client_name or "")
        span.set_attribute("mem0.query", query)
        span.set_attribute("mem0.search.limit", numberOfHits)
        span.set_attribute("mem0.search.page", page)

        if not uid:
            error = AssertionError("Error: user_id not provided")
            _record_exception(span, error)
            raise error
        if not client_name:
            error = AssertionError("Error: client_name not provided")
            _record_exception(span, error)
            raise error

        try:
            with _TRACER.start_as_current_span("memory.search") as search_span:
                search_span.set_attribute("mem0.filters_present", bool(filters))
                memories = await search_memories(
                    query=query,
                    user_id=uid,
                    app_id=client_name,
                    numberOfHits=numberOfHits,
                    page=page,
                    filters=filters,
                )

            with _TRACER.start_as_current_span("memory.log_access"):
                await log_memory_access(
                    memories=memories,
                    user_id=uid,
                    app_id=client_name,
                    query=query,
                    access_type="search",
                )

            results_count = len(memories.get("results", [])) if isinstance(memories, dict) else len(memories)
            span.set_attribute("mem0.search.results_count", results_count)
            return json.dumps(memories, indent=2)
        except AssertionError as e:
            _record_exception(span, e)
            logging.exception(f"Error searching memory: {e}")
            raise
        except ValueError as e:
            _record_exception(span, e)
            logging.exception(f"Error searching memory: {e}")
            raise ValueError(f"Error searching memory: {e}")
        except Exception as e:
            _record_exception(span, e)
            logging.exception(e)
            raise MemoryError(f"Error searching memory: {e}")

@mcp.tool(description="List all memories in the user's memory")
async def list_memories() -> str:
    logging.info("List Memories called")

    with _TRACER.start_as_current_span("mcp.tool.list_memories", kind=SpanKind.INTERNAL) as span:
        uid = user_id_var.get(None)
        client_name = client_name_var.get(None)
        span.set_attribute("mem0.user_id", uid or "")
        span.set_attribute("mem0.client_name", client_name or "")

        if not uid:
            error = AssertionError("Error: user_id not provided")
            _record_exception(span, error)
            raise error
        if not client_name:
            error = AssertionError("Error: client_name not provided")
            _record_exception(span, error)
            raise error

        memory_client = get_memory_client_safe()
        if not memory_client:
            error = AssertionError("Error: Memory system is currently unavailable. Please try again later.")
            _record_exception(span, error)
            raise error

        try:
            db = SessionLocal()
            try:
                with _TRACER.start_as_current_span("db.get_user_and_app"):
                    user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

                with _TRACER.start_as_current_span("memory_client.get_all"):
                    memories = memory_client.get_all(user_id=uid)

                filtered_memories: List[Dict[str, Any]] = []
                with _TRACER.start_as_current_span("db.filter_memories"):
                    user_memories = db.query(Memory).filter(Memory.user_id == user.id).all()
                    accessible_memory_ids = [
                        memory.id
                        for memory in user_memories
                        if check_memory_access_permissions(db, memory, user, app_id=app.id)
                    ]

                    if isinstance(memories, dict) and "results" in memories:
                        for memory_data in memories["results"]:
                            if "id" not in memory_data:
                                continue
                            memory_id = uuid.UUID(memory_data["id"])
                            if memory_id in accessible_memory_ids:
                                access_log = MemoryAccessLog(
                                    memory_id=memory_id,
                                    app_id=app.id,
                                    access_type="list",
                                    metadata_={"hash": memory_data.get("hash")},
                                )
                                db.add(access_log)
                                filtered_memories.append(memory_data)
                    else:
                        for memory in memories:
                            memory_id = uuid.UUID(memory["id"])
                            memory_obj = db.query(Memory).filter(Memory.id == memory_id).first()
                            if memory_obj and check_memory_access_permissions(db, memory_obj, user, app_id=app.id):
                                access_log = MemoryAccessLog(
                                    memory_id=memory_id,
                                    app_id=app.id,
                                    access_type="list",
                                    metadata_={"hash": memory.get("hash")},
                                )
                                db.add(access_log)
                                filtered_memories.append(memory)

                with _TRACER.start_as_current_span("db.commit"):
                    db.commit()

                span.set_attribute("mem0.list.results_count", len(filtered_memories))
                return json.dumps(filtered_memories, indent=2)
            finally:
                db.close()
        except AssertionError as e:
            _record_exception(span, e)
            logging.exception(f"Error getting memories: {e}")
            raise
        except ValueError as e:
            _record_exception(span, e)
            logging.exception(f"Error getting memories: {e}")
            raise ValueError(f"Error getting memories: {e}")
        except Exception as e:
            _record_exception(span, e)
            logging.exception(f"Error getting memories: {e}")
            raise MemoryError(f"Error searching memory: {e}")

#LMAO why is this even a tool?
@mcp.tool(description="Delete all memories in the user's memory")
async def delete_all_memories() -> str:
    logging.warning("Delete All Memories called")

    with _TRACER.start_as_current_span("mcp.tool.delete_all_memories", kind=SpanKind.INTERNAL) as span:
        uid = user_id_var.get(None)
        client_name = client_name_var.get(None)
        span.set_attribute("mem0.user_id", uid or "")
        span.set_attribute("mem0.client_name", client_name or "")

        if not uid:
            error = AssertionError("Error: user_id not provided")
            _record_exception(span, error)
            raise error
        if not client_name:
            error = AssertionError("Error: client_name not provided")
            _record_exception(span, error)
            raise error

        memory_client = get_memory_client_safe()
        if not memory_client:
            error = AssertionError("Error: Memory system is currently unavailable. Please try again later.")
            _record_exception(span, error)
            raise error

        try:
            db = SessionLocal()
            try:
                with _TRACER.start_as_current_span("db.get_user_and_app"):
                    user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

                with _TRACER.start_as_current_span("db.fetch_memories"):
                    user_memories = db.query(Memory).filter(Memory.user_id == user.id).all()
                    accessible_memory_ids = [
                        memory.id
                        for memory in user_memories
                        if check_memory_access_permissions(db, memory, user, app_id=app.id)
                    ]

                span.set_attribute("mem0.delete.count", len(accessible_memory_ids))

                with _TRACER.start_as_current_span("memory_client.delete_batch"):
                    for memory_id in accessible_memory_ids:
                        try:
                            memory_client.delete(memory_id)
                        except Exception as delete_error:  # pragma: no cover - best effort cleanup
                            logging.warning(
                                "Failed to delete memory %s from vector store: %s",
                                memory_id,
                                delete_error,
                            )

                now = datetime.datetime.now(datetime.UTC)
                with _TRACER.start_as_current_span("db.mark_deleted"):
                    for memory_id in accessible_memory_ids:
                        memory = db.query(Memory).filter(Memory.id == memory_id).first()
                        if not memory:
                            continue
                        memory.state = MemoryState.deleted
                        memory.deleted_at = now

                        history = MemoryStatusHistory(
                            memory_id=memory_id,
                            changed_by=user.id,
                            old_state=MemoryState.active,
                            new_state=MemoryState.deleted,
                        )
                        db.add(history)

                        access_log = MemoryAccessLog(
                            memory_id=memory_id,
                            app_id=app.id,
                            access_type="delete_all",
                            metadata_={"operation": "bulk_delete"},
                        )
                        db.add(access_log)

                with _TRACER.start_as_current_span("db.commit"):
                    db.commit()

                return "Successfully deleted all memories"
            finally:
                db.close()
        except AssertionError as e:
            _record_exception(span, e)
            logging.exception(f"Error deleting memories: {e}")
            raise
        except ValueError as e:
            _record_exception(span, e)
            logging.exception(f"Error deleting memories: {e}")
            raise ValueError(f"Error deleting memories: {e}")
        except Exception as e:
            _record_exception(span, e)
            logging.exception(f"Error deleting memories: {e}")
            raise MemoryError(f"Error deleting memories: {e}")


@mcp_router.get("/{client_name}/sse")
async def handle_sse(request: Request, client_name: str, user: User = Depends(get_user_record)):
    """Handle SSE connections for a specific user and client.

    The route keeps the `{user_id}` path parameter for backward compatibility,
    but the authenticated user (via `get_user_record`) is used as the source
    of truth. The path `user_id` is ignored.
    """
    # Use authenticated user's external id and provided client_name
    uid = user.user_id
    user_token = user_id_var.set(uid or "")
    client_token = client_name_var.set(client_name or "")

    trace_token = _attach_trace_context_from_request(request)
    try:
        with _TRACER.start_as_current_span("mcp.sse.connect", kind=SpanKind.SERVER) as span:
            span.set_attribute("mem0.user_id", uid or "")
            span.set_attribute("mem0.client_name", client_name or "")
            try:
                # Handle SSE connection
                async with sse.connect_sse(
                    request.scope,
                    request.receive,
                    request._send,
                ) as (read_stream, write_stream):
                    await mcp._mcp_server.run(
                        read_stream,
                        write_stream,
                        mcp._mcp_server.create_initialization_options(),
                    )
            except Exception as exc:
                _record_exception(span, exc)
                raise
    finally:
        _detach_trace_context(trace_token)
        # Clean up context variables
        user_id_var.reset(user_token)
        client_name_var.reset(client_token)


@mcp_router.post("/messages")
async def handle_get_message(request: Request, user: User = Depends(get_user_record)):
    """Handle POST messages for SSE while ensuring user is authenticated.
    The authenticated user is obtained via `get_user_record`.
    """
    uid = user.user_id
    user_token = user_id_var.set(uid or "")
    trace_token = _attach_trace_context_from_request(request)
    try:
        with _TRACER.start_as_current_span("mcp.sse.messages", kind=SpanKind.SERVER) as span:
            span.set_attribute("mem0.user_id", uid or "")
            try:
                return await handle_post_message(request)
            except Exception as exc:
                _record_exception(span, exc)
                raise
    finally:
        _detach_trace_context(trace_token)
        user_id_var.reset(user_token)

@mcp_router.post("/{client_name}/sse/messages")
async def handle_post_message_route(request: Request, client_name: str, user: User = Depends(get_user_record)):
    """Handle POST messages for SSE while setting authenticated user context.

    The `{user_id}` path parameter is accepted for compatibility but ignored in
    favor of the authenticated user obtained via `get_user_record`.
    """
    uid = user.user_id
    user_token = user_id_var.set(uid or "")
    client_token = client_name_var.set(client_name or "")
    trace_token = _attach_trace_context_from_request(request)
    try:
        with _TRACER.start_as_current_span("mcp.sse.post_message", kind=SpanKind.SERVER) as span:
            span.set_attribute("mem0.user_id", uid or "")
            span.set_attribute("mem0.client_name", client_name or "")
            try:
                return await handle_post_message(request)
            except Exception as exc:
                _record_exception(span, exc)
                raise
    finally:
        _detach_trace_context(trace_token)
        user_id_var.reset(user_token)
        client_name_var.reset(client_token)

async def handle_post_message(request: Request):
    """Handle POST messages for SSE"""
    trace_token = _attach_trace_context_from_request(request)
    try:
        with _TRACER.start_as_current_span("mcp.sse.handle_post_message", kind=SpanKind.INTERNAL) as span:
            try:
                body = await request.body()

                # Create a simple receive function that returns the body
                async def receive():
                    return {"type": "http.request", "body": body, "more_body": False}

                # Create a simple send function that does nothing
                async def send(message):
                    return {}

                # Call handle_post_message with the correct arguments
                await sse.handle_post_message(request.scope, receive, send)

                # Return a success response
                return {"status": "ok"}
            except Exception as exc:
                _record_exception(span, exc)
                raise
    finally:
        _detach_trace_context(trace_token)


def setup_mcp_server(app: FastAPI):
    """Setup MCP server with the FastAPI application"""
    mcp._mcp_server.name = "mem0-mcp-server"

    # Include MCP router in the FastAPI app
    app.include_router(mcp_router)

