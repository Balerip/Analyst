from typing import Any, Union, Optional

import pandas as pd
from mindsdb_sql.parser.ast import Join
from mindsdb_sql.parser.ast.base import ASTNode
from mindsdb.integrations.libs.response import HandlerResponse, HandlerStatusResponse


class BaseHandler:
    """ Base class for handlers

    Base class for handlers that associate a source of information with the
    broader MindsDB ecosystem via SQL commands.
    """

    def __init__(self, name: str):
        """ constructor
        Args:
            name (str): the handler name
        """
        self.is_connected: bool = False
        self.name = name

    def connect(self) -> HandlerStatusResponse:
        """ Set up any connections required by the handler

        Should return output of check_connection() method after attempting
        connection. Should switch self.is_connected.

        Returns:
            HandlerStatusResponse
        """
        raise NotImplementedError()

    def disconnect(self):
        """ Close any existing connections

        Should switch self.is_connected.
        """
        self.is_connected = False
        return

    def check_connection(self) -> HandlerStatusResponse:
        """ Check connection to the handler

        Returns:
            HandlerStatusResponse
        """
        raise NotImplementedError()

    def native_query(self, query: Any) -> HandlerResponse:
        """Receive raw query and act upon it somehow.

        Args:
            query (Any): query in native format (str for sql databases,
                dict for mongo, etc)

        Returns:
            HandlerResponse
        """
        raise NotImplementedError()

    def query(self, query: ASTNode) -> HandlerResponse:
        """Receive query as AST (abstract syntax tree) and act upon it somehow.

        Args:
            query (ASTNode): sql query represented as AST. May be any kind
                of query: SELECT, INSERT, DELETE, etc

        Returns:
            HandlerResponse
        """
        raise NotImplementedError()

    def get_tables(self) -> HandlerResponse:
        """ Return list of entities

        Return list of entities that will be accesible as tables.

        Returns:
            HandlerResponse: shoud have same columns as information_schema.tables
                (https://dev.mysql.com/doc/refman/8.0/en/information-schema-tables-table.html)
                Column 'TABLE_NAME' is mandatory, other is optional.
        """
        raise NotImplementedError()

    def get_columns(self, table_name: str) -> HandlerResponse:
        """ Returns a list of entity columns

        Args:
            table_name (str): name of one of tables returned by self.get_tables()

        Returns:
            HandlerResponse: shoud have same columns as information_schema.columns
                (https://dev.mysql.com/doc/refman/8.0/en/information-schema-columns-table.html)
                Column 'COLUMN_NAME' is mandatory, other is optional. Hightly
                recomended to define also 'DATA_TYPE': it should be one of
                python data types (by default it str).
        """
        raise NotImplementedError()


class DatabaseHandler(BaseHandler):
    """
    Base class for handlers associated to data storage systems (e.g. databases, data warehouses, streaming services, etc.)
    """
    def __init__(self, name: str):
        super().__init__(name)


class PredictiveHandler(BaseHandler):
    """
    DEPRECATED.

    Base class for handlers associated to predictive systems.
    """
    def __init__(self, name: str):
        super().__init__(name)


class BaseMLEngine:
    """
    Base class for integration engine to connect with other Machine Learning libraries/frameworks.

    An instance of this class will be generated, used, and destroyed for each interaction with the underlying framework.
    """

    def __init__(self, model_storage, engine_storage) -> None:
        """
        Initialize any objects, fields or parameters required by the ML engine.

        At least, two storage objects should be available:
            - model_storage: stores models in the file system (path specified in MindsDB config).
            - engine_storage: stores model-related metadata in an internal MindsDB database.
        """
        self.model_storage = model_storage
        self.engine_storage = engine_storage

    def create_engine(self, connection_args: dict):
        """
        Optional.

        Used to connect with external sources (e.g. a REST API) that the engine will require to use any other methods.
        """
        raise NotImplementedError

    def create(self, target: str, df: Optional = Union[None, pd.DataFrame], args: Optional = dict) -> None:
        """
        Registers a model inside the engine registry for later usage.

        Normally, an input dataframe is required to train the model.
        However, some integrations may merely require registering the model instead of training, in which case `df` can be omitted.

        Any other arguments required to register the model can be passed in an `args` dictionary.
        """
        raise NotImplementedError

    def update(self, df: Optional = Union[None, pd.DataFrame]) -> None:
        """
        Optional.

        Used to update/fine-tune/adjust a pre-existing model without resetting the internal state (e.g. weights).

        Its availability will depend on underlying integration support, as not all ML models can be partially updated.
        """
        raise NotImplementedError

    def predict(self, df: pd.DataFrame, args: Optional = dict) -> pd.DataFrame:
        """
        Calls a model with some input dataframe `df`, and optionally some arguments `args`.

        The expected output is a dataframe with the predicted values in the target-named column.
        Additional columns can be present, and will be considered row-wise explanations if their names finish with `_explain`.
        """
        raise NotImplementedError

    def describe(self, key: Optional[None]) -> pd.DataFrame:
        """
        Optional.

        When called, this method provides global model insights, e.g. framework-level parameters used in training.
        """
        raise NotImplementedError
