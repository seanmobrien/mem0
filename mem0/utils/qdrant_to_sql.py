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


def convert_qdrant_filter_to_sql(
    qdrant_filter: models.Filter
) -> Dict[str, Union[str, List[Any]]]:
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
    filter_dict = qdrant_filter.model_dump() if hasattr(qdrant_filter, 'model_dump') else qdrant_filter.dict()
    
    clauses = []
    params = []
    
    # Process 'must' conditions (all must be true - use AND)
    if filter_dict.get('must'):
        must_clauses, must_params = _process_conditions(filter_dict['must'])
        if must_clauses:
            clauses.append(f"({' AND '.join(must_clauses)})")
            params.extend(must_params)
    
    # Process 'must_not' conditions (none must be true - use NOT)
    if filter_dict.get('must_not'):
        must_not_clauses, must_not_params = _process_conditions(filter_dict['must_not'])
        if must_not_clauses:
            clauses.append(f"NOT ({' OR '.join(must_not_clauses)})")
            params.extend(must_not_params)
    
    # Process 'should' conditions (at least one should be true - use OR)
    if filter_dict.get('should'):
        should_clauses, should_params = _process_conditions(filter_dict['should'])
        if should_clauses:
            clauses.append(f"({' OR '.join(should_clauses)})")
            params.extend(should_params)
    
    # Combine all clauses with AND
    final_clause = ' AND '.join(clauses) if clauses else ''
    
    return {
        'clause': final_clause,
        'params': params
    }


def _process_conditions(
    conditions: List[Dict[str, Any]]
) -> Tuple[List[str], List[Any]]:
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
        if 'has_id' in condition and 'key' not in condition:
            clause, condition_params = _process_has_id_condition(condition)
        else:
            clause, condition_params = _process_field_condition(condition)
            
        if clause:
            clauses.append(clause)
            params.extend(condition_params)
    
    return clauses, params


def _process_has_id_condition(
    condition: Dict[str, Any]
) -> Tuple[str, List[Any]]:
    """
    Process a HasIdCondition into a SQL clause that checks the 'id' column.
    
    Args:
        condition: HasIdCondition dictionary with 'has_id' key
        
    Returns:
        Tuple of (clause, params)
    """
    has_id_list = condition.get('has_id', [])
    
    if not has_id_list:
        # Empty has_id list means no match
        return "FALSE", []
    
    # Convert all values to strings for consistency
    params = [str(id_val) if id_val is not None else None for id_val in has_id_list]
    
    # Detect if all params are UUIDs (simple check: 36 chars and 4 dashes)
    def is_uuid(val):
        return (
            isinstance(val, str)
            and len(val) == 36
            and val.count('-') == 4
        )
    all_uuids = all(is_uuid(p) for p in params if p is not None)

    placeholders = ["%s" for _ in params]
    if all_uuids:
        clause = f"id::uuid = ANY(ARRAY[{', '.join(placeholders)}]::uuid[])"
    else:
        clause = f"id = ANY(ARRAY[{', '.join(placeholders)}]::text[])"
    
    return clause, params


def _process_field_condition(
    condition: Dict[str, Any]
) -> Tuple[str, List[Any]]:
    """
    Process a single field condition into a SQL clause.
    
    Args:
        condition: Field condition dictionary
        
    Returns:
        Tuple of (clause, params)
    """
    key = condition.get('key')
    if not key:
        return '', []
    
    # Handle different condition types
    if condition.get('match'):
        return _process_match_condition(key, condition['match'])
    elif condition.get('range'):
        return _process_range_condition(key, condition['range'])
    elif condition.get('is_empty') is not None:
        return _process_is_empty_condition(key, condition['is_empty'])
    elif condition.get('is_null') is not None:
        return _process_is_null_condition(key, condition['is_null'])
    elif condition.get('values_count'):
        return _process_values_count_condition(key, condition['values_count'])
    
    return '', []


def _process_match_condition(
    key: str, 
    match: Dict[str, Any]
) -> Tuple[str, List[Any]]:
    """Process match conditions (exact value or any of values)."""
    params = []
    
    if 'value' in match:
        # Single value match
        clause = f"payload->>'{key}' = %s"
        params.append(str(match['value']) if match['value'] is not None else None)
    elif 'any' in match:
        # Match any of the values
        values = match['any']
        if values:
            placeholders = ["%s" for _ in values]
            clause = f"payload->>'{key}' = ANY(ARRAY[{', '.join(placeholders)}])"
            params.extend(str(v) if v is not None else None for v in values)
        else:
            clause = "FALSE"  # Empty array means no match
    else:
        return '', []
    
    return clause, params


def _process_range_condition(
    key: str, 
    range_condition: Dict[str, Any]
) -> Tuple[str, List[Any]]:
    """Process range conditions (gte, lte, gt, lt)."""
    clauses = []
    params = []
    
    # Handle different range operators
    if 'gte' in range_condition and range_condition['gte'] is not None:
        clauses.append(f"(payload->>'{key}')::numeric >= %s")
        params.append(range_condition['gte'])
    
    if 'gt' in range_condition and range_condition['gt'] is not None:
        clauses.append(f"(payload->>'{key}')::numeric > %s")
        params.append(range_condition['gt'])
    
    if 'lte' in range_condition and range_condition['lte'] is not None:
        clauses.append(f"(payload->>'{key}')::numeric <= %s")
        params.append(range_condition['lte'])
    
    if 'lt' in range_condition and range_condition['lt'] is not None:
        clauses.append(f"(payload->>'{key}')::numeric < %s")
        params.append(range_condition['lt'])
    
    clause = ' AND '.join(clauses) if clauses else ''
    return clause, params


def _process_is_empty_condition(
    key: str, 
    is_empty: bool
) -> Tuple[str, List[Any]]:
    """Process is_empty conditions."""
    if is_empty:
        # Check if array is empty or null
        clause = f"(payload->>'{key}' IS NULL OR jsonb_array_length(payload->>'{key}') = 0)"
    else:
        # Check if array is not empty
        clause = f"(payload->>'{key}' IS NOT NULL AND jsonb_array_length(payload->>'{key}') > 0)"
    
    return clause, []


def _process_is_null_condition(
    key: str, 
    is_null: bool
) -> Tuple[str, List[Any]]:
    """Process is_null conditions."""
    if is_null:
        clause = f"payload->>'{key}' IS NULL"
    else:
        clause = f"payload->>'{key}' IS NOT NULL"
    
    return clause, []


def _process_values_count_condition(
    key: str, 
    values_count: Dict[str, Any]
) -> Tuple[str, List[Any]]:
    """Process values_count conditions (for array length)."""
    clauses = []
    params = []
    
    if 'gte' in values_count and values_count['gte'] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') >= %s")
        params.append(values_count['gte'])
    
    if 'gt' in values_count and values_count['gt'] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') > %s")
        params.append(values_count['gt'])
    
    if 'lte' in values_count and values_count['lte'] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') <= %s")
        params.append(values_count['lte'])
    
    if 'lt' in values_count and values_count['lt'] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') < %s")
        params.append(values_count['lt'])
    
    clause = ' AND '.join(clauses) if clauses else ''
    return clause, params