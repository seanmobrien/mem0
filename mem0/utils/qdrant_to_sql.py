"""
Utility functions to convert Qdrant filter objects to PostgreSQL-compatible WHERE clauses.

This module provides functionality to convert qdrant_client.http.models.Filter objects
into PostgreSQL WHERE clauses with parameter binding for JSON field filtering.
"""

from typing import Any, Dict, List, Tuple, Union

try:
    from qdrant_client.http import models
except ImportError:
    raise ImportError("Qdrant requires extra dependencies. Install with `pip install embedchain[qdrant]`") from None


def convert_filter_to_sql(
    qdrant_filter: models.Filter, 
    initial_param_index: int = 1
) -> Dict[str, Union[str, List[Any]]]:
    """
    Convert a Qdrant Filter object to a PostgreSQL-compatible WHERE clause and parameters.
    
    Args:
        qdrant_filter: The Qdrant Filter object to convert
        initial_param_index: Starting index for parameter placeholders (default: 1)
    
    Returns:
        Dict with 'clause' (str) and 'params' (list) keys
        
    Example:
        filter_obj = models.Filter(
            must=[models.FieldCondition(key="city", match=models.MatchValue(value="London"))]
        )
        result = convert_filter_to_sql(filter_obj)
        # Returns: {"clause": "payload->>'city' = $1", "params": ["London"]}
    """
    if not isinstance(qdrant_filter, models.Filter):
        raise TypeError("Expected qdrant_client.http.models.Filter object")
    
    # Convert filter to dict for easier processing
    filter_dict = qdrant_filter.model_dump() if hasattr(qdrant_filter, 'model_dump') else qdrant_filter.dict()
    
    clauses = []
    params = []
    param_index = initial_param_index
    
    # Process 'must' conditions (all must be true - use AND)
    if filter_dict.get('must'):
        must_clauses, must_params, param_index = _process_conditions(
            filter_dict['must'], param_index
        )
        if must_clauses:
            clauses.append(f"({' AND '.join(must_clauses)})")
            params.extend(must_params)
    
    # Process 'must_not' conditions (none must be true - use NOT)
    if filter_dict.get('must_not'):
        must_not_clauses, must_not_params, param_index = _process_conditions(
            filter_dict['must_not'], param_index
        )
        if must_not_clauses:
            clauses.append(f"NOT ({' OR '.join(must_not_clauses)})")
            params.extend(must_not_params)
    
    # Process 'should' conditions (at least one should be true - use OR)
    if filter_dict.get('should'):
        should_clauses, should_params, param_index = _process_conditions(
            filter_dict['should'], param_index
        )
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
    conditions: List[Dict[str, Any]], 
    param_index: int
) -> Tuple[List[str], List[Any], int]:
    """
    Process a list of field conditions into SQL clauses.
    
    Args:
        conditions: List of condition dictionaries
        param_index: Current parameter index
        
    Returns:
        Tuple of (clauses, params, next_param_index)
    """
    clauses = []
    params = []
    
    for condition in conditions:
        if not condition:
            continue
            
        clause, condition_params, param_index = _process_field_condition(condition, param_index)
        if clause:
            clauses.append(clause)
            params.extend(condition_params)
    
    return clauses, params, param_index


def _process_field_condition(
    condition: Dict[str, Any], 
    param_index: int
) -> Tuple[str, List[Any], int]:
    """
    Process a single field condition into a SQL clause.
    
    Args:
        condition: Field condition dictionary
        param_index: Current parameter index
        
    Returns:
        Tuple of (clause, params, next_param_index)
    """
    key = condition.get('key')
    if not key:
        return '', [], param_index
    
    # Handle different condition types
    if condition.get('match'):
        return _process_match_condition(key, condition['match'], param_index)
    elif condition.get('range'):
        return _process_range_condition(key, condition['range'], param_index)
    elif condition.get('is_empty') is not None:
        return _process_is_empty_condition(key, condition['is_empty'], param_index)
    elif condition.get('is_null') is not None:
        return _process_is_null_condition(key, condition['is_null'], param_index)
    elif condition.get('values_count'):
        return _process_values_count_condition(key, condition['values_count'], param_index)
    
    return '', [], param_index


def _process_match_condition(
    key: str, 
    match: Dict[str, Any], 
    param_index: int
) -> Tuple[str, List[Any], int]:
    """Process match conditions (exact value or any of values)."""
    params = []
    
    if 'value' in match:
        # Single value match
        clause = f"payload->>'{key}' = %s"
        params.append(str(match['value']) if match['value'] is not None else None)
        param_index += 1
    elif 'any' in match:
        # Match any of the values
        values = match['any']
        if values:
            placeholders = [f"%s" for i in range(len(values))]
            clause = f"payload->>'{key}' = ANY(ARRAY[{', '.join(placeholders)}])"
            params.extend(str(v) if v is not None else None for v in values)
            param_index += len(values)
        else:
            clause = "FALSE"  # Empty array means no match
    else:
        return '', [], param_index
    
    return clause, params, param_index


def _process_range_condition(
    key: str, 
    range_condition: Dict[str, Any], 
    param_index: int
) -> Tuple[str, List[Any], int]:
    """Process range conditions (gte, lte, gt, lt)."""
    clauses = []
    params = []
    
    # Handle different range operators
    if 'gte' in range_condition and range_condition['gte'] is not None:
        clauses.append(f"(payload->>'{key}')::numeric >= %s")
        params.append(range_condition['gte'])
        param_index += 1
    
    if 'gt' in range_condition and range_condition['gt'] is not None:
        clauses.append(f"(payload->>'{key}')::numeric > %s")
        params.append(range_condition['gt'])
        param_index += 1
    
    if 'lte' in range_condition and range_condition['lte'] is not None:
        clauses.append(f"(payload->>'{key}')::numeric <= %s")
        params.append(range_condition['lte'])
        param_index += 1
    
    if 'lt' in range_condition and range_condition['lt'] is not None:
        clauses.append(f"(payload->>'{key}')::numeric < %s")
        params.append(range_condition['lt'])
        param_index += 1
    
    clause = ' AND '.join(clauses) if clauses else ''
    return clause, params, param_index


def _process_is_empty_condition(
    key: str, 
    is_empty: bool, 
    param_index: int
) -> Tuple[str, List[Any], int]:
    """Process is_empty conditions."""
    if is_empty:
        # Check if array is empty or null
        clause = f"(payload->>'{key}' IS NULL OR jsonb_array_length(payload->>'{key}') = 0)"
    else:
        # Check if array is not empty
        clause = f"(payload->>'{key}' IS NOT NULL AND jsonb_array_length(payload->>'{key}') > 0)"
    
    return clause, [], param_index


def _process_is_null_condition(
    key: str, 
    is_null: bool, 
    param_index: int
) -> Tuple[str, List[Any], int]:
    """Process is_null conditions."""
    if is_null:
        clause = f"payload->>'{key}' IS NULL"
    else:
        clause = f"payload->>'{key}' IS NOT NULL"
    
    return clause, [], param_index


def _process_values_count_condition(
    key: str, 
    values_count: Dict[str, Any], 
    param_index: int
) -> Tuple[str, List[Any], int]:
    """Process values_count conditions (for array length)."""
    clauses = []
    params = []
    
    if 'gte' in values_count and values_count['gte'] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') >= %s")
        params.append(values_count['gte'])
        param_index += 1
    
    if 'gt' in values_count and values_count['gt'] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') > %s")
        params.append(values_count['gt'])
        param_index += 1
    
    if 'lte' in values_count and values_count['lte'] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') <= %s")
        params.append(values_count['lte'])
        param_index += 1
    
    if 'lt' in values_count and values_count['lt'] is not None:
        clauses.append(f"jsonb_array_length(payload->>'{key}') < %s")
        params.append(values_count['lt'])
        param_index += 1
    
    clause = ' AND '.join(clauses) if clauses else ''
    return clause, params, param_index