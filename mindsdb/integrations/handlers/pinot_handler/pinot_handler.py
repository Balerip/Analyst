from typing import Optional
from collections import OrderedDict

import pandas as pd
import pinotdb
import requests
from requests.exceptions import InvalidSchema
import json

from mindsdb_sql import parse_sql
from mindsdb_sql.render.sqlalchemy_render import SqlalchemyRender
from mindsdb.integrations.libs.base_handler import DatabaseHandler
from pinotdb.sqlalchemy import PinotDialect

from mindsdb_sql.parser.ast.base import ASTNode

from mindsdb.utilities.log import log
from mindsdb.integrations.libs.response import (
    HandlerStatusResponse as StatusResponse,
    HandlerResponse as Response,
    RESPONSE_TYPE
)
from mindsdb.integrations.libs.const import HANDLER_CONNECTION_ARG_TYPE as ARG_TYPE


class PinotHandler(DatabaseHandler):
    """
    This handler handles connection and execution of the Apache Pinot statements.
    """

    name = 'pinot'

    def __init__(self, name: str, connection_data: Optional[dict], **kwargs):
        """
        Initialize the handler.
        Args:
            name (str): name of particular handler instance
            connection_data (dict): parameters for connecting to the database
            **kwargs: arbitrary keyword arguments.
        """
        super().__init__(name)
        self.parser = parse_sql
        self.dialect = 'pinot'

        optional_parameters = ['username', 'password', 'verify_ssl']
        for parameter in optional_parameters:
            if parameter not in connection_data:
                connection_data[parameter] = None

        if 'scheme' not in connection_data:
            connection_data['scheme'] = 'http'

        self.connection_data = connection_data
        self.kwargs = kwargs

        self.connection = None
        self.is_connected = False

    def __del__(self):
        if self.is_connected is True:
            self.disconnect()

    def connect(self) -> StatusResponse:
        """
        Set up the connection required by the handler.
        Returns:
            HandlerStatusResponse
        """

        if self.is_connected is True:
            return self.connection

        self.connection = pinotdb.connect(
            host=self.connection_data['host'],
            port=self.connection_data['broker_port'],
            path=self.connection_data['path'],
            scheme=self.connection_data['scheme'],
            username=self.connection_data['username'],
            password=self.connection_data['password'],
            verify_ssl=json.loads(self.connection_data['verify_ssl'].lower())
        )
        self.is_connected = True

        return self.connection

    def disconnect(self):
        """
        Close any existing connections.
        """

        if self.is_connected is False:
            return

        self.connection.close()
        self.is_connected = False
        return self.is_connected

    def check_connection(self) -> StatusResponse:
        """
        Check connection to the handler.
        Returns:
            HandlerStatusResponse
        """

        response = StatusResponse(False)
        need_to_close = self.is_connected is False

        try:
            self.connect()
            response.success = True
        except Exception as e:
            log.error(f'Error connecting to Pinot, {e}!')
            response.error_message = str(e)
        finally:
            if response.success is True and need_to_close:
                self.disconnect()
            if response.success is False and self.is_connected is True:
                self.is_connected = False

        return response

    def native_query(self, query: str) -> StatusResponse:
        """
        Receive raw query and act upon it somehow.
        Args:
            query (str): query in native format
        Returns:
            HandlerResponse
        """

        need_to_close = self.is_connected is False

        connection = self.connect()
        cursor = connection.cursor()

        try:
            cursor.execute(query)
            result = cursor.fetchall()
            if result:
                response = Response(
                    RESPONSE_TYPE.TABLE,
                    data_frame=pd.DataFrame(
                        result,
                        columns=[x[0] for x in cursor.description]
                    )
                )
            else:
                connection.commit()
                response = Response(RESPONSE_TYPE.OK)
        except Exception as e:
            log.error(f'Error running query: {query} on Pinot!')
            response = Response(
                RESPONSE_TYPE.ERROR,
                error_message=str(e)
            )

        cursor.close()
        if need_to_close is True:
            self.disconnect()

        return response

    def query(self, query: ASTNode) -> StatusResponse:
        """
        Receive query as AST (abstract syntax tree) and act upon it somehow.
        Args:
            query (ASTNode): sql query represented as AST. May be any kind
                of query: SELECT, INTSERT, DELETE, etc
        Returns:
            HandlerResponse
        """
        renderer = SqlalchemyRender(PinotDialect)
        query_str = renderer.get_string(query, with_failback=True)
        return self.native_query(query_str)

    def get_tables(self) -> StatusResponse:
        """
        Return list of entities that will be accessible as tables.
        Returns:
            HandlerResponse
        """

        api_url = f"{self.connection_data['host']}:{self.connection_data['controller_port']}/tables"
        try:
            result = requests.get(api_url)
        except InvalidSchema as e:
            api_url = self.connection_data['scheme'] + api_url
            result = requests.get(api_url)

        response = Response(
            RESPONSE_TYPE.TABLE,
            data_frame=pd.DataFrame(
                json.loads(result.content)['tables'],
                columns=['table_name']
            )
        )

        return response

    def get_columns(self, table_name: str) -> StatusResponse:
        """
        Returns a list of entity columns.
        Args:
            table_name (str): name of one of tables returned by self.get_tables()
        Returns:
            HandlerResponse
        """

        api_url = f"{self.connection_data['host']}:{self.connection_data['controller_port']}/tables/{table_name}/schema"
        try:
            result = requests.get(api_url)
        except InvalidSchema as e:
            api_url = self.connection_data['scheme'] + api_url
            result = requests.get(api_url)

        df = pd.DataFrame(json.loads(result.content)['dimensionFieldSpecs'])
        df = df.rename(columns={'name': 'column_name', 'dataType': 'data_type'})

        response = Response(
            RESPONSE_TYPE.TABLE,
            data_frame=df
        )

        return response


connection_args = OrderedDict(
    host={
        'type': ARG_TYPE.STR,
        'description': 'The host name or IP address of the Apache Pinot cluster.'
    },
    broker_port={
        'type': ARG_TYPE.INT,
        'description': 'The port that the Broker of the Apache Pinot cluster is running on.'
    },
    controller_port={
        'type': ARG_TYPE.INT,
        'description': 'The port that the Controller of the Apache Pinot cluster is running on.'
    },
    path={
        'type': ARG_TYPE.STR,
        'description': 'The query path.'
    },
    scheme={
        'type': ARG_TYPE.STR,
        'description': 'The URI schema. This parameter is optional and the default will be https.'
    },
    username={
        'type': ARG_TYPE.STR,
        'description': 'The user name used to authenticate with the Apache Pinot cluster. This parameter is optional.'
    },
    password={
        'type': ARG_TYPE.STR,
        'description': 'The password used to authenticate with the Apache Pinot cluster. This parameter is optional.'
    },
    verify_ssl={
        'type': ARG_TYPE.STR,
        'description': 'The flag for whether SSL certificates should be verified or not. This parameter is optional and '
                       'if specified, it should be either True or False'
    },
)

connection_args_example = OrderedDict(
    host='localhost',
    broker_port=8000,
    controller_port=9000,
    path='/query/sql',
    scheme='http'
)