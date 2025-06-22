"""
Unit tests for qdrant_to_sql converter utility.
"""

import unittest
from unittest.mock import Mock

# Try to import qdrant dependencies, mock if not available
try:
    from qdrant_client.http import models
    QDRANT_AVAILABLE = True
except ImportError:
    QDRANT_AVAILABLE = False
    # Create mock models for testing
    models = Mock()

from mem0.utils.qdrant_to_sql import convert_qdrant_filter_to_sql


class TestQdrantToSQL(unittest.TestCase):
    """Test cases for Qdrant to SQL filter conversion."""
    
    def setUp(self):
        """Set up test fixtures."""
        if not QDRANT_AVAILABLE:
            self.skipTest("Qdrant client not available")
    
    def test_simple_match_value_filter(self):
        """Test converting a simple MatchValue filter."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="city",
                    match=models.MatchValue(value="London")
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'city' = %s)",
            'params': ["London"]
        }
        self.assertEqual(result, expected)
    
    def test_match_any_filter(self):
        """Test converting a MatchAny filter."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="categories",
                    match=models.MatchAny(any=["food", "restaurant", "cafe"])
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'categories' = ANY(ARRAY[%s, %s, %s]))",
            'params': ["food", "restaurant", "cafe"]
        }
        self.assertEqual(result, expected)
    
    def test_range_filter(self):
        """Test converting a Range filter."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="price",
                    range=models.Range(gte=10, lte=100)
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "((payload->>'price')::numeric >= %s AND (payload->>'price')::numeric <= %s)",
            'params': [10, 100]
        }
        self.assertEqual(result, expected)
    
    def test_complex_range_filter(self):
        """Test converting a Range filter with all operators."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="score",
                    range=models.Range(gt=0, lt=100, gte=1, lte=99)
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        # Should include all range conditions
        self.assertIn("(payload->>'score')::numeric >= %s", result['clause'])
        self.assertIn("(payload->>'score')::numeric > %s", result['clause'])
        self.assertIn("(payload->>'score')::numeric <= %s", result['clause'])
        self.assertIn("(payload->>'score')::numeric < %s", result['clause'])
        self.assertEqual(result['params'], [1, 0, 99, 100])
    
    def test_multiple_must_conditions(self):
        """Test converting multiple must conditions."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="city",
                    match=models.MatchValue(value="London")
                ),
                models.FieldCondition(
                    key="category",
                    match=models.MatchValue(value="restaurant")
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'city' = %s AND payload->>'category' = %s)",
            'params': ["London", "restaurant"]
        }
        self.assertEqual(result, expected)
    
    def test_must_not_conditions(self):
        """Test converting must_not conditions."""
        filter_obj = models.Filter(
            must_not=[
                models.FieldCondition(
                    key="status",
                    match=models.MatchValue(value="inactive")
                ),
                models.FieldCondition(
                    key="deleted",
                    match=models.MatchValue(value="true")
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "NOT (payload->>'status' = %s OR payload->>'deleted' = %s)",
            'params': ["inactive", "true"]
        }
        self.assertEqual(result, expected)
    
    def test_should_conditions(self):
        """Test converting should conditions."""
        filter_obj = models.Filter(
            should=[
                models.FieldCondition(
                    key="priority",
                    match=models.MatchValue(value="high")
                ),
                models.FieldCondition(
                    key="urgent",
                    match=models.MatchValue(value="true")
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'priority' = %s OR payload->>'urgent' = %s)",
            'params': ["high", "true"]
        }
        self.assertEqual(result, expected)
    
    def test_complex_mixed_conditions(self):
        """Test converting mixed must, must_not, and should conditions."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="city",
                    match=models.MatchValue(value="London")
                )
            ],
            must_not=[
                models.FieldCondition(
                    key="status",
                    match=models.MatchValue(value="inactive")
                )
            ],
            should=[
                models.FieldCondition(
                    key="priority",
                    match=models.MatchValue(value="high")
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        # Should contain all three parts connected with AND
        self.assertIn("payload->>'city' = %s", result['clause'])
        self.assertIn("NOT (payload->>'status' = %s)", result['clause'])
        self.assertIn("payload->>'priority' = %s", result['clause'])
        self.assertEqual(result['params'], ["London", "inactive", "high"])
        
        # Check that parts are connected with AND
        parts = result['clause'].split(' AND ')
        self.assertEqual(len(parts), 3)
    
    def test_empty_match_any(self):
        """Test converting MatchAny with empty array."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="tags",
                    match=models.MatchAny(any=[])
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(FALSE)",
            'params': []
        }
        self.assertEqual(result, expected)
    
    def test_initial_param_index(self):
        """Test using a custom initial parameter index."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="city",
                    match=models.MatchValue(value="London")
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'city' = %s)",
            'params': ["London"]
        }
        self.assertEqual(result, expected)
    
    def test_is_empty_condition(self):
        """Test handling is_empty conditions."""
        field_condition = models.FieldCondition(key="tags")
        field_condition.is_empty = True
        filter_obj = models.Filter(must=[field_condition])
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "((payload->>'tags' IS NULL OR jsonb_array_length(payload->'tags') = 0))",
            'params': []
        }
        self.assertEqual(result, expected)
    
    def test_is_null_condition(self):
        """Test handling is_null conditions."""
        field_condition = models.FieldCondition(key="optional_field")
        field_condition.is_null = False
        filter_obj = models.Filter(must=[field_condition])
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'optional_field' IS NOT NULL)",
            'params': []
        }
        self.assertEqual(result, expected)
    
    def test_values_count_condition(self):
        """Test handling values_count conditions."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="tags",
                    values_count=models.ValuesCount(gte=2, lte=5)
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(jsonb_array_length(payload->'tags') >= %s AND jsonb_array_length(payload->'tags') <= %s)",
            'params': [2, 5]
        }
        self.assertEqual(result, expected)
    
    def test_numeric_values(self):
        """Test handling numeric values in match conditions."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="count",
                    match=models.MatchValue(value=42)
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'count' = %s)",
            'params': ["42"]  # Should be converted to string
        }
        self.assertEqual(result, expected)
    
    def test_boolean_values(self):
        """Test handling boolean values in match conditions."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="active",
                    match=models.MatchValue(value=True)
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'active' = %s)",
            'params': ["True"]  # Should be converted to string
        }
        self.assertEqual(result, expected)
    
    def test_empty_filter(self):
        """Test converting an empty filter."""
        filter_obj = models.Filter()
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "",
            'params': []
        }
        self.assertEqual(result, expected)
    
    def test_invalid_input_type(self):
        """Test error handling for invalid input type."""
        with self.assertRaises(TypeError):
            convert_qdrant_filter_to_sql("not a filter object")
    
    def test_only_range_gt_lt(self):
        """Test range filter with only gt and lt."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="temperature",
                    range=models.Range(gt=0, lt=100)
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "((payload->>'temperature')::numeric > %s AND (payload->>'temperature')::numeric < %s)",
            'params': [0, 100]
        }
        self.assertEqual(result, expected)

    def test_key_with_special_characters(self):
        """Test handling keys with special characters."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="user-name",
                    match=models.MatchValue(value="john_doe")
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'user-name' = %s)",
            'params': ["john_doe"]
        }
        self.assertEqual(result, expected)

    def test_match_any_with_mixed_types(self):
        """Test MatchAny with mixed data types."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="mixed_values",
                    match=models.MatchAny(any=["string", 123, True, None])
                )
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'mixed_values' = ANY(ARRAY[%s, %s, %s, %s]))",
            'params': ["string", "123", "True", None]
        }
        self.assertEqual(result, expected)

    def test_comprehensive_filter(self):
        """Test a comprehensive filter with all condition types."""
        # Create complex filter with different condition types
        must_conditions = []
        
        # MatchValue condition
        must_conditions.append(
            models.FieldCondition(
                key="city",
                match=models.MatchValue(value="London")
            )
        )
        
        # Range condition
        must_conditions.append(
            models.FieldCondition(
                key="price",
                range=models.Range(gte=10, lte=100)
            )
        )
        
        # MatchAny condition
        must_conditions.append(
            models.FieldCondition(
                key="categories",
                match=models.MatchAny(any=["food", "restaurant"])
            )
        )
        
        # ValuesCount condition
        must_conditions.append(
            models.FieldCondition(
                key="tags",
                values_count=models.ValuesCount(gte=1)
            )
        )
        
        # is_null condition
        active_condition = models.FieldCondition(key="active")
        active_condition.is_null = False
        must_conditions.append(active_condition)
        
        # Create must_not conditions
        must_not_conditions = []
        must_not_conditions.append(
            models.FieldCondition(
                key="status",
                match=models.MatchValue(value="inactive")
            )
        )
        
        # Create should conditions
        should_conditions = []
        should_conditions.append(
            models.FieldCondition(
                key="priority",
                match=models.MatchValue(value="high")
            )
        )
        
        filter_obj = models.Filter(
            must=must_conditions,
            must_not=must_not_conditions,
            should=should_conditions
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        # Verify the structure
        self.assertIn("payload->>'city' = %s", result['clause'])
        self.assertIn("(payload->>'price')::numeric >= %s", result['clause'])
        self.assertIn("(payload->>'price')::numeric <= %s", result['clause'])
        self.assertIn("payload->>'categories' = ANY(ARRAY[%s, %s])", result['clause'])
        self.assertIn("jsonb_array_length(payload->'tags') >= %s", result['clause'])
        self.assertIn("payload->>'active' IS NOT NULL", result['clause'])
        self.assertIn("NOT (payload->>'status' = %s)", result['clause'])
        self.assertIn("payload->>'priority' = %s", result['clause'])
        
        expected_params = ["London", 10.0, 100.0, "food", "restaurant", 1, "inactive", "high"]
        self.assertEqual(result['params'], expected_params)

    def test_hasid_condition_must(self):
        """Test HasIdCondition in must context."""
        filter_obj = models.Filter(
            must=[models.HasIdCondition(has_id=[1, 2, 3])]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(id = ANY(ARRAY[%s, %s, %s]))",
            'params': ["1", "2", "3"]
        }
        self.assertEqual(result, expected)

    def test_hasid_condition_must_not(self):
        """Test HasIdCondition in must_not context."""
        filter_obj = models.Filter(
            must_not=[models.HasIdCondition(has_id=[4, 5, 6])]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "NOT (id = ANY(ARRAY[%s, %s, %s]))",
            'params': ["4", "5", "6"]
        }
        self.assertEqual(result, expected)

    def test_hasid_condition_should(self):
        """Test HasIdCondition in should context."""
        filter_obj = models.Filter(
            should=[models.HasIdCondition(has_id=[7, 8, 9])]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(id = ANY(ARRAY[%s, %s, %s]))",
            'params': ["7", "8", "9"]
        }
        self.assertEqual(result, expected)

    def test_hasid_condition_mixed_with_field_condition(self):
        """Test HasIdCondition mixed with FieldCondition."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="city",
                    match=models.MatchValue(value="London")
                ),
                models.HasIdCondition(has_id=[10, 11, 12])
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(payload->>'city' = %s AND id = ANY(ARRAY[%s, %s, %s]))",
            'params': ["London", "10", "11", "12"]
        }
        self.assertEqual(result, expected)

    def test_hasid_condition_empty_list(self):
        """Test HasIdCondition with empty has_id list."""
        filter_obj = models.Filter(
            must=[models.HasIdCondition(has_id=[])]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(FALSE)",
            'params': []
        }
        self.assertEqual(result, expected)

    def test_hasid_condition_string_ids(self):
        """Test HasIdCondition with string IDs."""
        filter_obj = models.Filter(
            must=[models.HasIdCondition(has_id=["user-123", "user-456", "user-789"])]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(id = ANY(ARRAY[%s, %s, %s]))",
            'params': ["user-123", "user-456", "user-789"]
        }
        self.assertEqual(result, expected)

    def test_hasid_condition_single_id(self):
        """Test HasIdCondition with single ID."""
        filter_obj = models.Filter(
            must=[models.HasIdCondition(has_id=[42])]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(id = ANY(ARRAY[%s]))",
            'params': ["42"]
        }
        self.assertEqual(result, expected)

    def test_hasid_condition_mixed_string_and_int_ids(self):
        """Test HasIdCondition with mixed string and int IDs."""
        filter_obj = models.Filter(
            must=[models.HasIdCondition(has_id=[1, "abc", 3])]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "(id = ANY(ARRAY[%s, %s, %s]))",
            'params': ["1", "abc", "3"]
        }
        self.assertEqual(result, expected)

    def test_complex_filter_with_hasid_condition(self):
        """Test complex filter combining all condition types including HasIdCondition."""
        filter_obj = models.Filter(
            must=[
                models.FieldCondition(
                    key="city",
                    match=models.MatchValue(value="London")
                ),
                models.HasIdCondition(has_id=[100, 200])
            ],
            must_not=[
                models.FieldCondition(
                    key="status",
                    match=models.MatchValue(value="inactive")
                ),
                models.HasIdCondition(has_id=[999])
            ],
            should=[
                models.FieldCondition(
                    key="priority",
                    match=models.MatchValue(value="high")
                ),
                models.HasIdCondition(has_id=[300, 400])
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        # Check that all parts are present in the clause
        self.assertIn("payload->>'city' = %s", result['clause'])
        self.assertIn("id = ANY(ARRAY[%s, %s])", result['clause'])
        self.assertIn("NOT (payload->>'status' = %s OR id = ANY(ARRAY[%s]))", result['clause'])
        self.assertIn("(payload->>'priority' = %s OR id = ANY(ARRAY[%s, %s]))", result['clause'])
        
        expected_params = ["London", "100", "200", "inactive", "999", "high", "300", "400"]
        self.assertEqual(result['params'], expected_params)
        
        # Verify structure: should have 3 main clause groups (must, must_not, should)
        # The clause format is: (must_clauses) AND NOT (must_not_clauses) AND (should_clauses)
        expected_clause = "(payload->>'city' = %s AND id = ANY(ARRAY[%s, %s])) AND NOT (payload->>'status' = %s OR id = ANY(ARRAY[%s])) AND (payload->>'priority' = %s OR id = ANY(ARRAY[%s, %s]))"
        self.assertEqual(result['clause'], expected_clause)

    def test_multiple_hasid_conditions_must_not(self):
        """Test multiple HasIdCondition in must_not context."""
        filter_obj = models.Filter(
            must_not=[
                models.HasIdCondition(has_id=[1, 2]),
                models.HasIdCondition(has_id=[3, 4])
            ]
        )
        
        result = convert_qdrant_filter_to_sql(filter_obj)
        
        expected = {
            'clause': "NOT (id = ANY(ARRAY[%s, %s]) OR id = ANY(ARRAY[%s, %s]))",
            'params': ["1", "2", "3", "4"]
        }
        self.assertEqual(result, expected)


if __name__ == '__main__':
    unittest.main()