from mediawikiapi import MediaWikiAPI

from mindsdb.integrations.handlers.mediawiki_handler.mediawiki_tables import PagesTable
from mindsdb.integrations.libs.api_handler import APIHandler
from mindsdb.integrations.libs.response import (
    HandlerStatusResponse as StatusResponse,
)

from mindsdb.utilities import log
from mindsdb_sql import parse_sql


class MediaWikiHandler(APIHandler):
    """
    The MediaWiki handler implementation.
    """

    name = 'mediawiki'

    def __init__(self, name: str, **kwargs):
        """
        Initialize the handler.
        Args:
            name (str): name of particular handler instance
            **kwargs: arbitrary keyword arguments.
        """
        super().__init__(name)

        self.kwargs = kwargs

        self.connection = None
        self.is_connected = False

        pages_data = PagesTable(self)
        self._register_table("pages", pages_data)

    def connect(self):
        """
        Set up the connection required by the handler.
        Returns
        -------
        StatusResponse
            connection object
        """
        if self.is_connected is True:
            return self.connection

        self.connection = MediaWikiAPI()

        self.is_connected = True

        return self.connection