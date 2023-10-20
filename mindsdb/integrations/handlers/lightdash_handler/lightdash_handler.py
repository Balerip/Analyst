from mindsdb_sql import parse_sql

from mindsdb.integrations.handlers.lightdash_handler.api import Lightdash
from mindsdb.integrations.handlers.lightdash_handler.lightdash_tables import (
    # TODO: Create tables
)
from mindsdb.integrations.libs.api_handler import APIHandler
from mindsdb.integrations.libs.response import HandlerStatusResponse as StatusResponse


class LightdashHandler(APIHandler):

    def __init__(self, name: str, **kwargs) -> None:
        super().__init__(name)
        self.connection = None
        self.is_connected = False
        self.api_key = kwargs.get("connection_data", {}).get("api_key", "")
        self.base_url = kwargs.get("connection_data", {}).get("base_url", "")
        _tables = [
            # TODO: Create tables
        ]
        for Table in _tables:
            self._register_table(Table.name, Table(self))
        self.connect()

    def connect(self) -> Lightdash:
        self.connection = Lightdash(self.base_url, self.api_key)
        return self.connection

    def check_connection(self) -> StatusResponse:
        response = StatusResponse(False)
        if self.connection and not self.connection.is_connected():
            return Response(
                RESPONSE_TYPE.ERROR,
                error_message="Client not connected"
            )
        return Response(RESPONSE_TYPE.OK)

    def native_query(self, query: str) -> StatusResponse:
        ast = parse_sql(query, dialect="mindsdb")
        return self.query(ast)
