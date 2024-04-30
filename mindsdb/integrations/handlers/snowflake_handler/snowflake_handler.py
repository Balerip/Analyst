from pandas import DataFrame
from snowflake import connector
from collections import OrderedDict
from snowflake.sqlalchemy import snowdialect

from mindsdb_sql.render.sqlalchemy_render import SqlalchemyRender
from mindsdb_sql.parser.ast.base import ASTNode

from mindsdb.integrations.libs.base import DatabaseHandler
from mindsdb.integrations.libs.response import (
    HandlerStatusResponse as StatusResponse,
    HandlerResponse as Response,
    RESPONSE_TYPE
)
from mindsdb.utilities import log
from mindsdb.integrations.libs.const import HANDLER_CONNECTION_ARG_TYPE as ARG_TYPE

logger = log.getLogger(__name__)


class SnowflakeHandler(DatabaseHandler):
    """
    This handler handles connection and execution of the Snowflake statements.
    """

    name = 'snowflake'

    def __init__(self, name, **kwargs):
        super().__init__(name)
        self.connection_data = kwargs.get('connection_data')
        self.renderer = SqlalchemyRender(snowdialect.dialect)

        self.is_connected = False
        self.connection = None

    def connect(self):
        """
        Establishes a connection to a Snowflake account.

        Raises:
            ValueError: If the required connection parameters are not provided.
            snowflake.connector.errors.Error: If an error occurs while connecting to the Snowflake account.

        Returns:
            snowflake.connector.connection.SnowflakeConnection: A connection object to the Snowflake account.
        """

        if self.is_connected is True:
            return self.connection

        # Mandatory connection parameters
        if not all(key in self.connection_data for key in ['account', 'user', 'password']):
            raise ValueError('Required parameters (account, user, password) must be provided.')

        config = {
            'account': self.connection_data.get('account'),
            'user': self.connection_data.get('user'),
            'password': self.connection_data.get('password')
        }

        # Optional connection parameters
        optional_params = ['database', 'schema', 'warehouse', 'role']
        for param in optional_params:
            if param in self.connection_data:
                config[param] = self.connection_data[param]

        try:
            self.connection = connector.connect(**config)
            self.is_connected = True
            return self.connection
        except connector.errors.Error as e:
            logger.error(f'Error connecting to Snowflake, {e}!')
            raise

    def disconnect(self):
        """
        Closes the connection to the Snowflake account if it's currently open.
        """

        if self.is_connected is False:
            return
        self.connection.close()
        self.is_connected = False

    def check_connection(self) -> StatusResponse:
        """
        Checks the status of the connection to the Snowflake account.

        Returns:
            StatusResponse: An object containing the success status and an error message if an error occurs.
        """

        response = StatusResponse(False)
        need_to_close = not self.is_connected

        try:
            connection = self.connect()

            # Execute a simple query to test the connection
            with connection.cursor() as cur:
                cur.execute('select 1;')
            response.success = True
        except (connector.errors.Error, ValueError) as e:
            logger.error(f'Error connecting to Snowflake, {e}!')
            response.error_message = str(e)

        if response.success and need_to_close:
            self.disconnect()

        elif not response.success and self.is_connected:
            self.is_connected = False

        return response

    def native_query(self, query: str) -> Response:
        """
        Executes a SQL query on the Snowflake account and returns the result.

        Args:
            query (str): The SQL query to be executed.

        Returns:
            Response: A response object containing the result of the query or an error message.
        """

        need_to_close = self.is_connected is False

        connection = self.connect()
        with connection.cursor(connector.DictCursor) as cur:
            try:
                cur.execute(query)
                result = cur.fetchall()
                if result:
                    response = Response(
                        RESPONSE_TYPE.TABLE,
                        DataFrame(
                            result,
                            columns=[x[0] for x in cur.description]
                        )
                    )
                else:
                    response = Response(RESPONSE_TYPE.OK)
            except Exception as e:
                logger.error(f'Error running query: {query} on Snowflake!')
                response = Response(
                    RESPONSE_TYPE.ERROR,
                    error_code=0,
                    error_message=str(e)
                )

        if need_to_close is True:
            self.disconnect()

        return response

    def query(self, query: ASTNode) -> Response:
        """
        Executes a SQL query represented by an ASTNode and retrieves the data.

        Args:
            query (ASTNode): An ASTNode representing the SQL query to be executed.

        Returns:
            Response: The response from the `native_query` method, containing the result of the SQL query execution.
        """

        query_str = self.renderer.get_string(query, with_failback=True)
        logger.debug(f"Executing SQL query: {query_str}")
        return self.native_query(query_str)

    def get_tables(self) -> Response:
        """
        Retrieves a list of all non-system tables and views in the current schema of the Snowflake account.

        Returns:
            Response: A response object containing the list of tables and views, formatted as per the `Response` class.
        """

        query = "SHOW TABLES;"
        result_tables = self.native_query(query)
        result_tables.data_frame = result_tables.data_frame.rename(columns={'name': 'table_name'})

        query = "SHOW VIEWS;"
        result_views = self.native_query(query)
        result_views.data_frame = result_views.data_frame.rename(columns={'name': 'table_name'})

        result = Response(RESPONSE_TYPE.TABLE)
        result.data_frame = result_tables.data_frame.append(result_views.data_frame, ignore_index=True)
        return result

    def get_columns(self, table_name) -> Response:
        """
        Retrieves column details for a specified table in the Snowflake account.

        Args:
            table_name (str): The name of the table for which to retrieve column information.

        Returns:
            Response: A response object containing the column details, formatted as per the `Response` class.
        Raises:
            ValueError: If the 'table_name' is not a valid string.
        """

        if not table_name or not isinstance(table_name, str):
            raise ValueError("Invalid table name provided.")

        query = f"SHOW COLUMNS IN TABLE {table_name};"
        result = self.native_query(query)
        return result


connection_args = OrderedDict(
    account={
        'type': ARG_TYPE.STR,
        'description': 'The Snowflake account name.',
        'required': False,
        'label': 'Server'
    },
    user={
        'type': ARG_TYPE.STR,
        'description': 'The user name used to authenticate with the Snowflake account.',
        'required': True,
        'label': 'User'
    },
    password={
        'type': ARG_TYPE.PWD,
        'description': 'The password to authenticate the user with the Snowflake account.',
        'required': True,
        'label': 'Password'
    },
    database={
        'type': ARG_TYPE.STR,
        'description': 'The database to use when connecting to the Snowflake account.',
        'required': True,
        'label': 'Database'
    },
    schema={
        'type': ARG_TYPE.STR,
        'description': 'The schema to use when connecting to the Snowflake account.',
        'required': False,
        'label': 'Schema'
    },
    warehouse={
        'type': ARG_TYPE.STR,
        'description': 'The warehouse to use when executing queries on the Snowflake account.',
        'required': False,
        'label': 'Warehouse'
    },
    role={
        'type': ARG_TYPE.STR,
        'description': 'The role to use when executing queries on the Snowflake account.',
        'required': False,
        'label': 'Role'
    }
)

connection_args_example = OrderedDict(
    account='abcxyz-1234567',
    user='user',
    password='password',
    database='test'
)
