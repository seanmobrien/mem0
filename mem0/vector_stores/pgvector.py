import json
import logging
from typing import List, Optional

from pydantic import BaseModel

try:
    import psycopg2
    from psycopg2.extras import execute_values
except ImportError:
    raise ImportError("The 'psycopg2' library is required. Please install it using 'pip install psycopg2'.")

from mem0.utils.qdrant_to_sql import convert_qdrant_filter_to_sql
from mem0.vector_stores.base import VectorStoreBase

logger = logging.getLogger(__name__)


class OutputData(BaseModel):
    id: Optional[str]
    score: Optional[float]
    payload: Optional[dict]


class PGVector(VectorStoreBase):
    def __init__(
        self,
        dbname,
        collection_name,
        embedding_model_dims,
        user,
        password,
        host,
        port,
        diskann,
        hnsw,
    ):
        """
        Initialize the PGVector database.

        Args:
            dbname (str): Database name
            collection_name (str): Collection name
            embedding_model_dims (int): Dimension of the embedding vector
            user (str): Database user
            password (str): Database password
            host (str, optional): Database host
            port (int, optional): Database port
            diskann (bool, optional): Use DiskANN for faster search
            hnsw (bool, optional): Use HNSW for faster search
        """
        self.collection_name = collection_name
        self.use_diskann = diskann
        self.use_hnsw = hnsw
        self.embedding_model_dims = embedding_model_dims

        self.conn = psycopg2.connect(dbname=dbname, user=user, password=password, host=host, port=port)
        self.cur = self.conn.cursor()

        collections = self.list_cols()
        if collection_name not in collections:
            self.create_col(embedding_model_dims)

    def _is_extension_installed(self, extension_name):
        """
        Check if a PostgreSQL extension is installed.

        Args:
            extension_name (str): Name of the extension to check.

        Returns:
            bool: True if the extension is installed, False otherwise.
        """
        self.cur.execute("SELECT * FROM pg_extension WHERE extname = %s", (extension_name,))
        return self.cur.fetchone() is not None

    def create_col(self, embedding_model_dims):
        """
        Create a new collection (table in PostgreSQL).
        Will also initialize vector search index if specified.

        Args:
            embedding_model_dims (int): Dimension of the embedding vector.
        """
        if not self._is_extension_installed("vector"):
            logger.info("Creating vector extension in PostgreSQL...")
            self.cur.execute("CREATE EXTENSION vector")
        
        self.cur.execute(
            f"""
            CREATE TABLE IF NOT EXISTS {self.collection_name} (
                id UUID PRIMARY KEY,
                vector vector({embedding_model_dims}),
                payload JSONB
            );
        """
        )

        if self.use_diskann and embedding_model_dims < 2000:
            # Check if vectorscale extension is installed
            # self.cur.execute("SELECT * FROM pg_extension WHERE extname = 'vectorscale'")
            if self._is_extension_installed("vectorscale") or self._is_extension_installed("pg_diskann"):
                # Create DiskANN index if extension is installed for faster search
                self.cur.execute(
                    f"""
                    CREATE INDEX IF NOT EXISTS {self.collection_name}_diskann_idx
                    ON {self.collection_name}
                    USING diskann (vector);
                """
                )
        elif self.use_hnsw:
            self.cur.execute(
                f"""
                CREATE INDEX IF NOT EXISTS {self.collection_name}_hnsw_idx
                ON {self.collection_name}
                USING hnsw (vector vector_cosine_ops)
            """
            )

        self.conn.commit()

    def _is_qdrant_filter_object(self, filters):
        """
        Check if the filters parameter is a qdrant Filter object.
        
        Args:
            filters: The filters parameter to check
            
        Returns:
            bool: True if it's a qdrant Filter object, False otherwise
        """
        # Check for qdrant Filter object attributes
        return hasattr(filters, 'model_dump') or hasattr(filters, 'dict')

    def _is_qdrant_like_filter(self, filters_dict):
        """
        Check if dictionary can be interpreted as a qdrant filter.
        
        A dictionary is considered qdrant-like if:
        - It contains qdrant filter keys (must, must_not, should, should_not)
        - The values of these keys are lists
        - The items in these lists are dictionaries with 'key' field (field conditions)
        
        Args:
            filters_dict (dict): Dictionary to check
            
        Returns:
            bool: True if it can be interpreted as a qdrant filter, False otherwise
        """
        if not isinstance(filters_dict, dict):
            return False
            
        # Check if it has qdrant filter keys
        qdrant_keys = {'must', 'must_not', 'should', 'should_not'}
        if not any(key in filters_dict for key in qdrant_keys):
            return False
        
        # Check if the values are lists and contain field-like conditions
        for key in qdrant_keys:
            if key in filters_dict:
                if not isinstance(filters_dict[key], list):
                    return False
                # Check if items in the list look like field conditions
                for condition in filters_dict[key]:
                    if not isinstance(condition, dict):
                        return False
                    # Should have 'key' field for field conditions
                    # or 'has_id' field for ID conditions
                    if 'key' not in condition and 'has_id' not in condition:
                        return False
        return True

    def _convert_dict_to_qdrant_filter(self, filters_dict):
        """
        Convert a dictionary with qdrant-like structure to a qdrant Filter object.
        
        Args:
            filters_dict (dict): Dictionary with qdrant-like structure
            
        Returns:
            qdrant Filter object
        """
        # Import qdrant models (assuming they're available since convert_qdrant_filter_to_sql uses them)
        try:
            from qdrant_client.http import models
        except ImportError:
            raise ImportError("Qdrant client is required for qdrant-like filter processing")
        
        # Convert dictionary conditions to qdrant objects
        def convert_condition(condition_dict):
            if 'has_id' in condition_dict:
                # HasIdCondition
                return models.HasIdCondition(has_id=condition_dict['has_id'])
            elif 'key' in condition_dict:
                # FieldCondition
                key = condition_dict['key']
                field_condition = models.FieldCondition(key=key)
                
                # Handle different condition types
                if 'match' in condition_dict:
                    match = condition_dict['match']
                    if 'value' in match:
                        field_condition.match = models.MatchValue(value=match['value'])
                    elif 'any' in match:
                        field_condition.match = models.MatchAny(any=match['any'])
                
                if 'range' in condition_dict:
                    range_dict = condition_dict['range']
                    field_condition.range = models.Range(**range_dict)
                
                if 'is_empty' in condition_dict:
                    field_condition.is_empty = condition_dict['is_empty']
                
                if 'is_null' in condition_dict:
                    field_condition.is_null = condition_dict['is_null']
                
                if 'values_count' in condition_dict:
                    values_count = condition_dict['values_count']
                    field_condition.values_count = models.ValuesCount(**values_count)
                
                return field_condition
            else:
                raise ValueError(f"Invalid condition format: {condition_dict}")
        
        # Build the filter
        filter_kwargs = {}
        
        for key in ['must', 'must_not', 'should', 'should_not']:
            if key in filters_dict:
                filter_kwargs[key] = [convert_condition(cond) for cond in filters_dict[key]]
        
        return models.Filter(**filter_kwargs)

    def insert(self, vectors, payloads=None, ids=None):
        """
        Insert vectors into a collection.

        Args:
            vectors (List[List[float]]): List of vectors to insert.
            payloads (List[Dict], optional): List of payloads corresponding to vectors.
            ids (List[str], optional): List of IDs corresponding to vectors.
        """
        logger.info(f"Inserting {len(vectors)} vectors into collection {self.collection_name}")
        json_payloads = [json.dumps(payload) for payload in payloads]

        data = [(id, vector, payload) for id, vector, payload in zip(ids, vectors, json_payloads)]
        execute_values(
            self.cur,
            f"INSERT INTO {self.collection_name} (id, vector, payload) VALUES %s",
            data,
        )
        self.conn.commit()

    def search(self, query, vectors, limit=5, filters=None, pageNumber = 1):
        """
        Search for similar vectors.

        Args:
            query (str): Query - Not really used, this isn't a hybrid search.
            vectors (List[float]): Query vector - This is where the real money is hiding.
            limit (int, optional): Number of results to return. Defaults to 5.
            filters (Dict, optional): Filters to apply to the search. Defaults to None. Supports:
                - qdrant.Filter objects
                - Dictionaries with qdrant-like structure (must, must_not, should, should_not keys)
                - Simple key/value dictionaries for equality filters on payload fields

        Returns:
            list: Search results.
        """
        filter_conditions = []
        filter_params = []

        if filters:
            if self._is_qdrant_filter_object(filters):
                # Case 1: qdrant Filter object - use existing logic
                parsed_filters = convert_qdrant_filter_to_sql(filters)
                filter_params.extend(parsed_filters['params'])
                filter_conditions.append(parsed_filters['clause'])
            elif isinstance(filters, dict):
                if self._is_qdrant_like_filter(filters):
                    # Case 2: Dictionary with qdrant-like structure
                    qdrant_filter = self._convert_dict_to_qdrant_filter(filters)
                    parsed_filters = convert_qdrant_filter_to_sql(qdrant_filter)
                    filter_params.extend(parsed_filters['params'])
                    filter_conditions.append(parsed_filters['clause'])
                else:
                    # Case 3: Simple key/value dictionary
                    for k, v in filters.items():
                        filter_conditions.append("payload->>%s = %s")
                        filter_params.extend([k, str(v)])
            else:
                # Fallback: try to use existing logic for backward compatibility
                parsed_filters = convert_qdrant_filter_to_sql(filters)
                filter_params.extend(parsed_filters['params'])
                filter_conditions.append(parsed_filters['clause'])

        filter_clause = "WHERE " + " AND ".join(filter_conditions) if filter_conditions else ""
        offset_clause = f"OFFSET {(pageNumber - 1) * limit}" if pageNumber > 1 else ""
        self.cur.execute(
            f"""
            SELECT id, vector <=> %s::vector AS distance, payload
            FROM {self.collection_name}
            {filter_clause}
            ORDER BY distance
            LIMIT %s {offset_clause}
        """,
            (vectors, *filter_params, limit),
        )

        results = self.cur.fetchall()
        return [OutputData(id=str(r[0]), score=float(r[1]), payload=r[2]) for r in results]

    def delete(self, vector_id):
        """
        Delete a vector by ID.

        Args:
            vector_id (str): ID of the vector to delete.
        """
        self.cur.execute(f"DELETE FROM {self.collection_name} WHERE id = %s", (vector_id,))
        self.conn.commit()

    def update(self, vector_id, vector=None, payload=None):
        """
        Update a vector and its payload.

        Args:
            vector_id (str): ID of the vector to update.
            vector (List[float], optional): Updated vector.
            payload (Dict, optional): Updated payload.
        """
        if vector:
            self.cur.execute(
                f"UPDATE {self.collection_name} SET vector = %s WHERE id = %s",
                (vector, vector_id),
            )
        if payload:
            self.cur.execute(
                f"UPDATE {self.collection_name} SET payload = %s WHERE id = %s",
                (psycopg2.extras.Json(payload), vector_id),
            )
        self.conn.commit()

    def get(self, vector_id) -> OutputData:
        """
        Retrieve a vector by ID.

        Args:
            vector_id (str): ID of the vector to retrieve.

        Returns:
            OutputData: Retrieved vector.
        """
        self.cur.execute(
            f"SELECT id, vector, payload FROM {self.collection_name} WHERE id = %s",
            (vector_id,),
        )
        result = self.cur.fetchone()
        if not result:
            return None
        return OutputData(id=str(result[0]), score=None, payload=result[2])

    def list_cols(self) -> List[str]:
        """
        List all collections.

        Returns:
            List[str]: List of collection names.
        """
        self.cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public'")
        return [row[0] for row in self.cur.fetchall()]

    def delete_col(self):
        """Delete a collection."""
        self.cur.execute(f"DROP TABLE IF EXISTS {self.collection_name}")
        self.conn.commit()

    def col_info(self):
        """
        Get information about a collection.

        Returns:
            Dict[str, Any]: Collection information.
        """
        self.cur.execute(
            f"""
            SELECT 
                table_name, 
                (SELECT COUNT(*) FROM {self.collection_name}) as row_count,
                (SELECT pg_size_pretty(pg_total_relation_size('{self.collection_name}'))) as total_size
            FROM information_schema.tables 
            WHERE table_schema = 'public' AND table_name = %s
        """,
            (self.collection_name,),
        )
        result = self.cur.fetchone()
        return {"name": result[0], "count": result[1], "size": result[2]}

    def list(self, filters=None, limit=100):
        """
        List all vectors in a collection.

        Args:
            filters (Dict, optional): Filters to apply to the list.
            limit (int, optional): Number of vectors to return. Defaults to 100.

        Returns:
            List[OutputData]: List of vectors.
        """
        filter_conditions = []
        filter_params = []

        if filters:
            parsed_filters = convert_qdrant_filter_to_sql(filters)
            filter_params.extend(parsed_filters['params'])

        filter_clause = "WHERE " + " AND ".join(filter_conditions) if filter_conditions else ""

        query = f"""
            SELECT id, vector, payload
            FROM {self.collection_name}
            {filter_clause}
            LIMIT %s
        """

        self.cur.execute(query, (*filter_params, limit))

        results = self.cur.fetchall()
        return [[OutputData(id=str(r[0]), score=None, payload=r[2]) for r in results]]

    def __del__(self):
        """
        Close the database connection when the object is deleted.
        """
        if hasattr(self, "cur"):
            self.cur.close()
        if hasattr(self, "conn"):
            self.conn.close()

    def reset(self):
        """Reset the index by deleting and recreating it."""
        logger.warning(f"Resetting index {self.collection_name}...")
        self.delete_col()
        self.create_col(self.embedding_model_dims)
