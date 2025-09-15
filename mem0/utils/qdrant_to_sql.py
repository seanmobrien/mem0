"""
Utility functions to convert Qdrant filter objects to PostgreSQL-compatible WHERE clauses.

This module provides functionality to convert qdrant_client.http.models.Filter objects
into PostgreSQL WHERE clauses with parameter binding for JSON field filtering.

Supported Qdrant filter conditions:
- FieldCondition: Filters on payload fields using match, range, is_empty, is_null, values_count
- HasIdCondition: Filters on record IDs directly using the 'id' column

Examples:
    Basic field filtering:
        filter_obj = models.Filter(
            must=[models.FieldCondition(key="city", match=models.MatchValue(value="London"))]
        )
        result = convert_filter_to_sql(filter_obj)
        # Returns: {"clause": "payload->>'city' = %s", "params": ["London"]}

    ID filtering:
        filter_obj = models.Filter(
            must=[models.HasIdCondition(has_id=[1, 2, 3])]
        )
        result = convert_filter_to_sql(filter_obj)
        # Returns: {"clause": "id = ANY(ARRAY[%s, %s, %s])", "params": ["1", "2", "3"]}

    Mixed filtering:
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(key="city", match=models.MatchValue(value="London")),
                models.HasIdCondition(has_id=[100, 200])
            ],
            must_not=[models.HasIdCondition(has_id=[999])]
        )
        result = convert_filter_to_sql(filter_obj)
        # Returns complex SQL combining field and ID filters
"""

from typing import Any, Dict, List, Tuple, Union

try:
    from qdrant_client.http import models
except ImportError:
    raise ImportError("Qdrant requires extra dependencies. Install with `pip install embedchain[qdrant]`") from None


def convert_qdrant_filter_to_sql(qdrant_filter: models.Filter) -> Dict[str, Union[str, List[Any]]]:
    """
    Convert a Qdrant Filter object to a PostgreSQL-compatible WHERE clause and parameters.

    Args:
        qdrant_filter: The Qdrant Filter object to convert

    Returns:
        Dict with 'clause' (str) and 'params' (list) keys

    Example:
        filter_obj = models.Filter(
            must=[models.FieldCondition(key="city", match=models.MatchValue(value="London"))]
        )
        result = convert_filter_to_sql(filter_obj)
        # Returns: {"clause": "payload->>'city' = %s", "params": ["London"]}
    """
    if not isinstance(qdrant_filter, models.Filter):
        raise TypeError("Expected qdrant_client.http.models.Filter object")

    # Convert filter to dict for easier processing
    filter_dict = qdrant_filter.model_dump() if hasattr(qdrant_filter, "model_dump") else qdrant_filter.dict()

    clauses = []
    params = []

    # Process 'must' conditions (all must be true - use AND)
    if filter_dict.get("must"):
        must_clauses, must_params = _process_conditions(filter_dict["must"])
        if must_clauses:
            clauses.append(f"({' AND '.join(must_clauses)})")
            params.extend(must_params)

    # Process 'must_not' conditions (none must be true - use NOT)
    if filter_dict.get("must_not"):
        must_not_clauses, must_not_params = _process_conditions(filter_dict["must_not"])
        if must_not_clauses:
            clauses.append(f"NOT ({' OR '.join(must_not_clauses)})")
            params.extend(must_not_params)

    # Process 'should' conditions (at least one should be true - use OR)
    if filter_dict.get("should"):
        should_clauses, should_params = _process_conditions(filter_dict["should"])
        if should_clauses:
            clauses.append(f"({' OR '.join(should_clauses)})")
            params.extend(should_params)

    # Combine all clauses with AND
    final_clause = " AND ".join(clauses) if clauses else ""

    return {"clause": final_clause, "params": params}


def _process_conditions(conditions: List[Dict[str, Any]]) -> Tuple[List[str], List[Any]]:
    """
    Process a list of field conditions into SQL clauses.

    Args:
        conditions: List of condition dictionaries

    Returns:
        Tuple of (clauses, params)
    """
    clauses = []
    params = []

    for condition in conditions:
        if not condition:
            continue

        # Check if this is a HasIdCondition
        if "has_id" in condition and "key" not in condition:
            clause, condition_params = _process_has_id_condition(condition)
        else:
            clause, condition_params = _process_field_condition(condition)

        if clause:
            clauses.append(clause)
            params.extend(condition_params)

    return clauses, params


def _process_has_id_condition(condition: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """
    Process a HasIdCondition into a SQL clause that checks the 'id' column.

    Args:
        condition: HasIdCondition dictionary with 'has_id' key

    Returns:
        Tuple of (clause, params)
    """
    has_id_list = condition.get("has_id", [])

    if not has_id_list:
        # Empty has_id list means no match
        return "FALSE", []

    # Convert all values to strings for consistency
    params = [str(id_val) if id_val is not None else None for id_val in has_id_list]

    # Detect if all params are UUIDs (simple check: 36 chars and 4 dashes)
    def is_uuid(val):
        return isinstance(val, str) and len(val) == 36 and val.count("-") == 4

    all_uuids = all(is_uuid(p) for p in params if p is not None)

    placeholders = ["%s" for _ in params]
    if all_uuids:
        clause = f"id::uuid = ANY(ARRAY[{', '.join(placeholders)}]::uuid[])"
    else:
        clause = f"id = ANY(ARRAY[{', '.join(placeholders)}]::text[])"

    return clause, params


def _process_field_condition(condition: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """
    Process a single field condition into a SQL clause.

    Args:
        condition: Field condition dictionary

    Returns:
        Tuple of (clause, params)
    """
    key = condition.get("key")
    if not key:
        return "", []

    # Handle different condition types
    if condition.get("match"):
        return _process_match_condition(key, condition["match"])
    elif condition.get("range"):
        return _process_range_condition(key, condition["range"])
    elif condition.get("is_empty") is not None:
        return _process_is_empty_condition(key, condition["is_empty"])
    elif condition.get("is_null") is not None:
        return _process_is_null_condition(key, condition["is_null"])
    elif condition.get("values_count"):
        return _process_values_count_condition(key, condition["values_count"])

    return "", []


def _process_match_condition(key: str, match: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """Process match conditions (exact value or any of values)."""
    params = []

    if "value" in match:
        # Single value match
        clause = f"payload->>'{key}' = %s"
        params.append(str(match["value"]) if match["value"] is not None else None)
    elif "any" in match:
        # Match any of the values
        values = match["any"]
        if values:
            placeholders = ["%s" for _ in values]
            clause = f"payload->>'{key}' = ANY(ARRAY[{', '.join(placeholders)}])"
            params.extend(str(v) if v is not None else None for v in values)
        else:
            clause = "FALSE"  # Empty array means no match
    else:
        return "", []

    return clause, params


def _process_range_condition(key: str, range_condition: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """Process range conditions (gte, lte, gt, lt)."""
    clauses = []
    params = []

    # Handle different range operators
    if "gte" in range_condition and range_condition["gte"] is not None:
        clauses.append(f"(payload->>'{key}')::numeric >= %s")
        params.append(range_condition["gte"])

    if "gt" in range_condition and range_condition["gt"] is not None:
        clauses.append(f"(payload->>'{key}')::numeric > %s")
        params.append(range_condition["gt"])

    if "lte" in range_condition and range_condition["lte"] is not None:
        clauses.append(f"(payload->>'{key}')::numeric <= %s")
        params.append(range_condition["lte"])

    if "lt" in range_condition and range_condition["lt"] is not None:
        clauses.append(f"(payload->>'{key}')::numeric < %s")
        params.append(range_condition["lt"])

    clause = " AND ".join(clauses) if clauses else ""
    return clause, params


def _process_is_empty_condition(key: str, is_empty: bool) -> Tuple[str, List[Any]]:
    """Process is_empty conditions."""
    if is_empty:
        # Check if array is empty or null
        clause = f"(payload->>'{key}' IS NULL OR jsonb_array_length(payload->>'{key}') = 0)"
    else:
        # Check if array is not empty
        clause = f"(payload->>'{key}' IS NOT NULL AND jsonb_array_length(payload->>'{key}') > 0)"

    return clause, []


def _process_is_null_condition(key: str, is_null: bool) -> Tuple[str, List[Any]]:
    """Process is_null conditions."""
    if is_null:
        clause = f"payload->>'{key}' IS NULL"
    else:
        clause = f"payload->>'{key}' IS NOT NULL"

    return clause, []


def _process_values_count_condition(key: str, values_count: Dict[str, Any]) -> Tuple[str, List[Any]]:
    """Process values_count conditions (for array length)."""
    clauses = []
    params = []

    if "gte" in values_count and values_count["gte"] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') >= %s")
        params.append(values_count["gte"])

    if "gt" in values_count and values_count["gt"] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') > %s")
        params.append(values_count["gt"])

    if "lte" in values_count and values_count["lte"] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') <= %s")
        params.append(values_count["lte"])

    if "lt" in values_count and values_count["lt"] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') < %s")
        params.append(values_count["lt"])

    clause = " AND ".join(clauses) if clauses else ""
    return clause, params


def is_qdrant_filter_object(filters):
    """
    Check if the filters parameter is a qdrant Filter object.

    Args:
        filters: The filters parameter to check

    Returns:
        bool: True if it's a qdrant Filter object, False otherwise
    """
    # Check for qdrant Filter object attributes
    return hasattr(filters, "model_dump") or hasattr(filters, "dict")


def is_qdrant_like_filter(filters_dict):
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
    qdrant_keys = {"must", "must_not", "should", "should_not"}
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
                if "key" not in condition and "has_id" not in condition:
                    return False
    return True


def convert_dict_to_qdrant_filter(filters_dict):
    """
    Convert a dictionary with qdrant-like structure to a qdrant Filter object.

    Args:
        filters_dict (dict): Dictionary with qdrant-like structure

    Returns:
        qdrant Filter object
    """

    # Convert dictionary conditions to qdrant objects
    def convert_condition(condition_dict):
        if "has_id" in condition_dict:
            # HasIdCondition
            return models.HasIdCondition(has_id=condition_dict["has_id"])
        elif "key" in condition_dict:
            # FieldCondition
            key = condition_dict["key"]
            field_condition = models.FieldCondition(key=key)

            # Handle different condition types
            if "match" in condition_dict:
                match = condition_dict["match"]
                if "value" in match:
                    field_condition.match = models.MatchValue(value=match["value"])
                elif "any" in match:
                    field_condition.match = models.MatchAny(any=match["any"])

            if "range" in condition_dict:
                range_dict = condition_dict["range"]
                field_condition.range = models.Range(**range_dict)

            if "is_empty" in condition_dict:
                field_condition.is_empty = condition_dict["is_empty"]

            if "is_null" in condition_dict:
                field_condition.is_null = condition_dict["is_null"]

            if "values_count" in condition_dict:
                values_count = condition_dict["values_count"]
                field_condition.values_count = models.ValuesCount(**values_count)

            return field_condition
        else:
            raise ValueError(f"Invalid condition format: {condition_dict}")

    # Build the filter
    filter_kwargs = {}

    for key in ["must", "must_not", "should", "should_not"]:
        if key in filters_dict:
            filter_kwargs[key] = [convert_condition(cond) for cond in filters_dict[key]]

    return models.Filter(**filter_kwargs)
