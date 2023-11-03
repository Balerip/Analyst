import os
import time
import pytest
import pandas as pd
from unittest.mock import patch
from mindsdb_sql import parse_sql
from mindsdb.integrations.handlers.anthropic_handler.anthropic_handler import AnthropicHandler
from ..executor_test_base import BaseExecutorTest


@pytest.mark.skipif(os.environ.get('ANTHROPIC_API_KEY') is None, reason='Missing API key!')
class TestAnthropic(BaseExecutorTest):
    """Test Class for Anthropic Integration Testing"""

    @staticmethod
    def get_api_key():
        """Retrieve Anthropic API key from environment variables"""
        return os.environ.get("ANTHROPIC_API_KEY")

    def setup_method(self, method):
        """Setup test environment, creating a project"""
        super().setup_method()
        self.run_sql("create database proj")
        self.run_sql(
            f"""
            CREATE ML_ENGINE anthropic
            FROM anthropic
            USING
            api_key = '{self.get_api_key()}';
            """
        )

    def wait_predictor(self, project, name, timeout=100):
        """
        Wait for the predictor to be created,
        raising an exception if predictor creation fails or exceeds timeout
        """
        for attempt in range(timeout):
            ret = self.run_sql(f"select * from {project}.models where name='{name}'")
            if not ret.empty:
                status = ret["STATUS"][0]
                if status == "complete":
                    return
                elif status == "error":
                    raise RuntimeError("Predictor failed", ret["ERROR"][0])
            time.sleep(0.5)
        raise RuntimeError("Predictor wasn't created")
    
    def run_sql(self, sql):
        """Execute SQL and return a DataFrame, raising an AssertionError if an error occurs"""
        ret = self.command_executor.execute_command(parse_sql(sql, dialect="mindsdb"))
        assert ret.error_code is None, f"SQL execution failed with error: {ret.error_code}"
        if ret.data is not None:
            columns = [col.alias if col.alias else col.name for col in ret.columns]
            return pd.DataFrame(ret.data, columns=columns)
    
    def test_invalid_anthropic_model_parameter(self):
        """Test for invalid Anthropic model parameter"""
        self.run_sql(
            f"""
            CREATE MODEL proj.test_anthropic_invalid_model
            PREDICT answer
            USING
                engine='anthropic',
                column='question',
                model='this-claude-does-not-exist',
                api_key='{self.get_api_key()}';
            """
        )
        with pytest.raises(Exception):
            self.wait_predictor("proj", "test_anthropic_invalid_model")

    def test_unknown_anthropic_model_argument(self):
        """Test for unknown argument when creating a Anthropic model"""
        self.run_sql(
            f"""
            CREATE MODEL proj.test_anthropic_unknown_argument
            PREDICT answer
            USING
                engine='anthropic',
                column='question',
                api_key='{self.get_api_key()}',
                evidently_wrong_argument='wrong value';
            """
        )
        with pytest.raises(Exception):
            self.wait_predictor("proj", "test_anthropic_unknown_argument")