import os
import pytest
from app.utils import client_config_factory

def test_env_graph_skip_db_removes_database(monkeypatch):
    monkeypatch.setenv('MEM0_PROVIDER_GRAPHSTORE', 'neo4j')
    monkeypatch.setenv('GRAPH_URI', 'neo4j+s://example.databases.neo4j.io')
    monkeypatch.setenv('GRAPH_USERNAME', 'alice')
    monkeypatch.setenv('GRAPH_PASSWORD', 'secret')
    monkeypatch.setenv('GRAPH_SKIP_DB', 'true')
    config = client_config_factory.get_default_memory_config(expandSecrets=True)
    assert 'graph_store' in config
    assert config['graph_skip_db'] is True
    assert 'database' not in config['graph_store']['config']

def test_env_graph_store_with_database(monkeypatch):
    monkeypatch.setenv('MEM0_PROVIDER_GRAPHSTORE', 'neo4j')
    monkeypatch.setenv('GRAPH_URI', 'neo4j+s://example.databases.neo4j.io')
    monkeypatch.setenv('GRAPH_USERNAME', 'alice')
    monkeypatch.setenv('GRAPH_PASSWORD', 'secret')
    monkeypatch.setenv('GRAPH_SKIP_DB', 'false')
    config = client_config_factory.get_default_memory_config(expandSecrets=True)
    assert 'graph_store' in config
    assert config['graph_skip_db'] is False
    # database is not set by default envs, so should not be present
    assert 'database' not in config['graph_store']['config']

def test_merge_graph_skip_db_from_db(monkeypatch):
    monkeypatch.delenv('GRAPH_SKIP_DB', raising=False)
    saved = {
        'mem0': {
            'graph_store': {
                'provider': 'neo4j',
                'config': {
                    'url': 'neo4j+s://saved.databases.neo4j.io',
                    'username': 'saved-user',
                    'password': 'saved-pass',
                    'database': 'saved-db',
                },
            },
            'graph_skip_db': True,
        }
    }
    orig = client_config_factory._get_config_from_database
    client_config_factory._get_config_from_database = lambda: saved
    try:
        config = client_config_factory.get_parsed_memory_config(expandSecrets=True)
        assert config['graph_skip_db'] is True
        assert 'database' not in config['graph_store']['config']
        assert config['graph_store']['config']['url'] == 'neo4j+s://saved.databases.neo4j.io'
    finally:
        client_config_factory._get_config_from_database = orig
