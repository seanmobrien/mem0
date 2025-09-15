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
from typing import Any, Dict, List, Mapping
from mcp.server.fastmcp import FastMCP, Context
from mcp.server.sse import SseServerTransport
from app.utils.memory import get_memory_client
from fastapi import FastAPI, HTTPException, Request, Depends
from fastapi.routing import APIRouter
import contextvars
import os
from dotenv import load_dotenv
from app.database import SessionLocal
from app.models import Memory, MemoryState, MemoryStatusHistory, MemoryAccessLog, User
from app.utils.db import get_user_and_app
from app.auth import get_user_record
import uuid
import datetime
from app.utils.permissions import check_memory_access_permissions
from app.utils.memory_client import search_memories, log_memory_access
from qdrant_client import models as qdrant_models
from typing import Union

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

# Create a router for MCP endpoints
mcp_router = APIRouter(prefix="/mcp")

# Initialize SSE transport
sse = SseServerTransport("/mcp/messages/")

@mcp.tool(description="Add a new memory. This method is called everytime the user informs anything about themselves, their preferences, or anything that has any relevant information which can be useful in the future conversation. This can also be called when the user asks you to remember something.  " +
          "Metadata can be provided to store additional information that can be useful for filtering or categorizing memories later.  Any arbitrary metadata can be provided, but some special keys include - 'created_at': when present, this will be used as the memory creation date.  This should always be set to the send date of the analyzed document.  'chat_thread': the thread ID of the chat where this message was sent.")
async def add_memories(text: str, metadata: Mapping[str, Any] = None) -> str | Mapping[str, str | List[Any] | Mapping[str, Any]]:
    if metadata is None:
        metadata = {}
    logging.info("Add Memory called with text: %s", text)
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)

    if not uid:
        raise AssertionError("Error: user_id not provided")
    if not client_name:
        raise AssertionError("Error: client_name not provided")

    # Get memory client safely
    memory_client = get_memory_client_safe()
    if not memory_client:
        raise AssertionError("Memory system is currently unavailable. Please try again later.")
        

    try:
        db = SessionLocal()
        try:
            # Get or create user and app
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Check if app is active
            if not app.is_active:
                raise ValueError(f"Error: App {app.name} is currently paused on OpenMemory. Cannot create new memories.")

            default_metadata = {
                "source_app": "openmemory",
                "mcp_client": client_name,
            }
            meta = { **default_metadata, **(metadata or {}) }

            response = memory_client.add(text,
                                         user_id=uid,
                                         metadata=meta)
            memory_timestamp = datetime.datetime.fromisoformat(meta.pop('created_at', datetime.datetime.now(datetime.UTC).isoformat()))

            # Process the response and update database
            if isinstance(response, dict) and 'results' in response:
                for result in response['results']:
                    memory_id = uuid.UUID(result['id'])
                    memory = db.query(Memory).filter(Memory.id == memory_id).first()

                    if result['event'] == 'ADD':
                        if not memory:
                            memory = Memory(
                                id=memory_id,
                                user_id=user.id,
                                app_id=app.id,
                                metadata=meta,
                                created_at=memory_timestamp,
                                content=result['memory'],
                                state=MemoryState.active
                            )
                            db.add(memory)
                        else:
                            memory.state = MemoryState.active
                            memory.content = result['memory']

                        # Create history entry
                        history = MemoryStatusHistory(
                            memory_id=memory_id,
                            changed_by=user.id,
                            changed_at=memory_timestamp ,
                            old_state=MemoryState.deleted if memory else None,
                            new_state=MemoryState.active
                        )
                        db.add(history)

                    elif result['event'] == 'DELETE':
                        if memory:
                            memory.state = MemoryState.deleted
                            memory.deleted_at = datetime.datetime.now(datetime.UTC)
                            # Create history entry
                            history = MemoryStatusHistory(
                                memory_id=memory_id,
                                changed_by=user.id,
                                old_state=MemoryState.active,
                                new_state=MemoryState.deleted
                            )
                            db.add(history)

                db.commit()

            return response
        finally:
            db.close()
    except AssertionError as e:
        logging.exception(f"Error adding to memory: {e}")
        raise e
    except ValueError as e:
        logging.exception(f"Error adding to memory: {e}")
        raise e
    except Exception as e:
        logging.exception(f"Error adding to memory: {e}")
        raise MemoryError(f"Error adding to memory: {e}")
        # return f"Error adding to memory: {e}"


@mcp.tool(description="Peforms a vector Search through stored memories. This method is called EVERYTIME the user asks anything.  Supports pagination if more context is necessary, but pay attention to the result score.")
async def search_memory(query: str, numberOfHits = 10, page = 1, filters: Union[qdrant_models.Filter, dict, None] = None) -> str:
    logging.info("Search Memory called with query: %s", query)
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        raise AssertionError("Error: user_id not provided")
    if not client_name:
        raise AssertionError("Error: client_name not provided")

    try:
        # Use the reusable search function
        memories = await search_memories(
            query=query,
            user_id=uid,
            app_id=client_name,
            numberOfHits=numberOfHits,
            page=page,
            filters=filters
        )
        
        # Log memory access
        await log_memory_access(
            memories=memories,
            user_id=uid,
            app_id=client_name,
            query=query,
            access_type="search"
        )
        
        return json.dumps(memories, indent=2)
    except AssertionError as e:
        logging.exception(f"Error searching memory: {e}")
        raise e
    except ValueError as e:
        logging.exception(f"Error searching memory: {e}")
        raise ValueError(f"Error searching memory: {e}")
    except Exception as e:
        logging.exception(e)
        raise MemoryError(f"Error searching memory: {e}")

@mcp.tool(description="List all memories in the user's memory")
async def list_memories() -> str:
    logging.info("List Memories called")
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        raise AssertionError("Error: user_id not provided")
    if not client_name:
        raise AssertionError("Error: client_name not provided")

    # Get memory client safely
    memory_client = get_memory_client_safe()
    if not memory_client:
        raise AssertionError("Error: Memory system is currently unavailable. Please try again later.")

    try:
        db = SessionLocal()
        try:
            # Get or create user and app
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            # Get all memories
            memories = memory_client.get_all(user_id=uid)
            filtered_memories = []

            # Filter memories based on permissions
            user_memories = db.query(Memory).filter(Memory.user_id == user.id).all()
            accessible_memory_ids = [memory.id for memory in user_memories if check_memory_access_permissions(db, memory, app.id)]
            if isinstance(memories, dict) and 'results' in memories:
                for memory_data in memories['results']:
                    if 'id' in memory_data:
                        memory_id = uuid.UUID(memory_data['id'])
                        if memory_id in accessible_memory_ids:
                            # Create access log entry
                            access_log = MemoryAccessLog(
                                memory_id=memory_id,
                                app_id=app.id,
                                access_type="list",
                                metadata_={
                                    "hash": memory_data.get('hash')
                                }
                            )
                            db.add(access_log)
                            filtered_memories.append(memory_data)
                db.commit()
            else:
                for memory in memories:
                    memory_id = uuid.UUID(memory['id'])
                    memory_obj = db.query(Memory).filter(Memory.id == memory_id).first()
                    if memory_obj and check_memory_access_permissions(db, memory_obj, app.id):
                        # Create access log entry
                        access_log = MemoryAccessLog(
                            memory_id=memory_id,
                            app_id=app.id,
                            access_type="list",
                            metadata_={
                                "hash": memory.get('hash')
                            }
                        )
                        db.add(access_log)
                        filtered_memories.append(memory)
                db.commit()
            return json.dumps(filtered_memories, indent=2)
        finally:
            db.close()
    except AssertionError as e:
        logging.exception(f"Error getting memories: {e}")
        raise e
    except ValueError as e:
        logging.exception(f"Error getting memories: {e}")
        raise ValueError(f"Error getting memories: {e}")
    except Exception as e:
        logging.exception(f"Error getting memories: {e}")
        raise MemoryError(f"Error searching memory: {e}")

#LMAO why is this even a tool?
@mcp.tool(description="Delete all memories in the user's memory")
async def delete_all_memories() -> str:
    logging.warning("Delete All Memories called")
    uid = user_id_var.get(None)
    client_name = client_name_var.get(None)
    if not uid:
        raise AssertionError("Error: user_id not provided")
    if not client_name:
        raise AssertionError("Error: client_name not provided")

    # Get memory client safely
    memory_client = get_memory_client_safe()
    if not memory_client:
        raise AssertionError("Error: Memory system is currently unavailable. Please try again later.")

    try:
        db = SessionLocal()
        try:
            # Get or create user and app
            user, app = get_user_and_app(db, user_id=uid, app_id=client_name)

            user_memories = db.query(Memory).filter(Memory.user_id == user.id).all()
            accessible_memory_ids = [memory.id for memory in user_memories if check_memory_access_permissions(db, memory, app.id)]

            # delete the accessible memories only
            for memory_id in accessible_memory_ids:
                try:
                    memory_client.delete(memory_id)
                except Exception as delete_error:
                    logging.warning(f"Failed to delete memory {memory_id} from vector store: {delete_error}")

            # Update each memory's state and create history entries
            now = datetime.datetime.now(datetime.UTC)
            for memory_id in accessible_memory_ids:
                memory = db.query(Memory).filter(Memory.id == memory_id).first()
                # Update memory state
                memory.state = MemoryState.deleted
                memory.deleted_at = now

                # Create history entry
                history = MemoryStatusHistory(
                    memory_id=memory_id,
                    changed_by=user.id,
                    old_state=MemoryState.active,
                    new_state=MemoryState.deleted
                )
                db.add(history)

                # Create access log entry
                access_log = MemoryAccessLog(
                    memory_id=memory_id,
                    app_id=app.id,
                    access_type="delete_all",
                    metadata_={"operation": "bulk_delete"}
                )
                db.add(access_log)

            db.commit()
            return "Successfully deleted all memories"
        finally:
            db.close()
    except AssertionError as e:
        logging.exception(f"Error deleting memories: {e}")
        raise e
    except ValueError as e:
        logging.exception(f"Error deleting memories: {e}")
        raise ValueError(f"Error deleting memories: {e}")
    except Exception as e:
        logging.exception(f"Error deleting memories: {e}")
        raise MemoryError(f"Error deleting memories: {e}")


@mcp_router.get("/{client_name}/sse/{user_id}")
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
    finally:
        # Clean up context variables
        user_id_var.reset(user_token)
        client_name_var.reset(client_token)


@mcp_router.post("/messages/")
async def handle_get_message(request: Request):
    return await handle_post_message(request)


@mcp_router.post("/{client_name}/sse/{user_id}/messages/")
async def handle_post_message_route(request: Request, client_name: str, user: User = Depends(get_user_record)):
    """Handle POST messages for SSE while setting authenticated user context.

    The `{user_id}` path parameter is accepted for compatibility but ignored in
    favor of the authenticated user obtained via `get_user_record`.
    """
    uid = user.user_id
    user_token = user_id_var.set(uid or "")
    client_token = client_name_var.set(client_name or "")
    try:
        return await handle_post_message(request)
    finally:
        user_id_var.reset(user_token)
        client_name_var.reset(client_token)

async def handle_post_message(request: Request):
    """Handle POST messages for SSE"""
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
    finally:
        pass
        # Clean up context variable
        # client_name_var.reset(client_token)


def setup_mcp_server(app: FastAPI):
    """Setup MCP server with the FastAPI application"""
    mcp._mcp_server.name = f"mem0-mcp-server"

    # Include MCP router in the FastAPI app
    app.include_router(mcp_router)

