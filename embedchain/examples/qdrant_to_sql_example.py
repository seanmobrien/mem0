"""
Example usage of the qdrant_to_sql converter.

This script demonstrates how to use the convert_filter_to_sql function
to convert Qdrant filters to PostgreSQL WHERE clauses.
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))

from qdrant_client.http import models

# Import the converter function directly
exec(open(os.path.join(os.path.dirname(__file__), '..', 'embedchain', 'vectordb', 'qdrant_to_sql.py')).read())


def main():
    """Demonstrate various filter conversions."""
    print("=== Qdrant to SQL Filter Conversion Examples ===\n")
    
    # Example 1: Simple MatchValue filter
    print("1. Simple MatchValue filter:")
    filter_obj = models.Filter(
        must=[
            models.FieldCondition(
                key="city",
                match=models.MatchValue(value="London")
            )
        ]
    )
    result = convert_filter_to_sql(filter_obj)
    print(f"   Input: Filter with city='London'")
    print(f"   Output: {result}")
    print()
    
    # Example 2: MatchAny filter
    print("2. MatchAny filter:")
    filter_obj = models.Filter(
        must=[
            models.FieldCondition(
                key="categories",
                match=models.MatchAny(any=["food", "restaurant", "cafe"])
            )
        ]
    )
    result = convert_filter_to_sql(filter_obj)
    print(f"   Input: Filter with categories in ['food', 'restaurant', 'cafe']")
    print(f"   Output: {result}")
    print()
    
    # Example 3: Range filter
    print("3. Range filter:")
    filter_obj = models.Filter(
        must=[
            models.FieldCondition(
                key="price",
                range=models.Range(gte=10, lte=100)
            )
        ]
    )
    result = convert_filter_to_sql(filter_obj)
    print(f"   Input: Filter with price between 10 and 100")
    print(f"   Output: {result}")
    print()
    
    # Example 4: Complex filter with multiple conditions
    print("4. Complex filter with multiple conditions:")
    filter_obj = models.Filter(
        must=[
            models.FieldCondition(
                key="city",
                match=models.MatchValue(value="London")
            ),
            models.FieldCondition(
                key="price",
                range=models.Range(lte=50)
            )
        ],
        must_not=[
            models.FieldCondition(
                key="status",
                match=models.MatchValue(value="inactive")
            )
        ]
    )
    result = convert_filter_to_sql(filter_obj)
    print(f"   Input: Filter with city='London' AND price<=50 AND status!='inactive'")
    print(f"   Output: {result}")
    print()
    
    # Example 5: Using custom parameter index
    print("5. Custom parameter index:")
    filter_obj = models.Filter(
        must=[
            models.FieldCondition(
                key="name",
                match=models.MatchValue(value="John")
            )
        ]
    )
    result = convert_filter_to_sql(filter_obj, initial_param_index=5)
    print(f"   Input: Filter with name='John' starting at parameter index 5")
    print(f"   Output: {result}")
    print()
    
    print("These SQL clauses can be used in PostgreSQL queries like:")
    print("SELECT * FROM table_name WHERE " + result['clause'] + ";")
    print("With parameters:", result['params'])


if __name__ == "__main__":
    main()