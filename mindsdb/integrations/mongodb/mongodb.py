import re

import certifi
from pymongo import MongoClient

from mindsdb.integrations.base import Integration


class MongoDB(Integration):
    def _query(self, query):
        return None

    def setup(self):
        pass

    def register_predictors(self, model_data_arr):
        pass

    def unregister_predictor(self, name):
        pass

    def check_connection(self):
        try:
            integration = self.config['integrations'][self.name]
            host = integration['host']
            user = integration['user']
            password = integration['password']

            kwargs = {}

            if isinstance(user, str) and len(user) > 0:
                kwargs['username'] = user

            if isinstance(password, str) and len(password) > 0:
                kwargs['password'] = password

            if re.match(r'\/\?.*tls=true', host.lower()):
                kwargs['tls'] = True

            if re.match(r'\/\?.*tls=false', host.lower()):
                kwargs['tls'] = False

            if re.match(r'.*\.mongodb.net', host.lower()) and kwargs.get('tls', None) is None:
                kwargs['tlsCAFile'] = certifi.where()
                if kwargs.get('tls', None) is None:
                    kwargs['tls'] = True

            server = MongoClient(
                host,
                port=integration.get('port', 27017),
                serverSelectionTimeoutMS=5000,
                **kwargs
            )
            server.server_info()
            connected = True
        except Exception:
            connected = False
        return connected


class MongoConnectionChecker:
    def __init__(self, **kwargs):
        self.host = kwargs.get("host")
        self.port = kwargs.get("port", 27017)
        self.user = kwargs.get("username")
        self.password = kwargs.get("password")

    def _handle_params(self):
        kwargs = {}
        if isinstance(self.user, str) and len(self.user) > 0:
            kwargs['username'] = self.user

        if isinstance(self.password, str) and len(self.password) > 0:
            kwargs['password'] = self.password

        if re.match(r'\/\?.*tls=true', self.host.lower()):
            kwargs['tls'] = True

        if re.match(r'\/\?.*tls=false', self.host.lower()):
            kwargs['tls'] = False

        if re.match(r'.*\.mongodb.net', self.host.lower()) and kwargs.get('tls', None) is None:
            kwargs['tlsCAFile'] = certifi.where()
            if kwargs.get('tls', None) is None:
                kwargs['tls'] = True

        return kwargs

    def check_connection(self):
        try:
            advanced_conn_params = self._handle_params()
            server = MongoClient(self.host,
                                 port=self.port,
                                 serverSelectionTimeoutMS=5000,
                                 **advanced_conn_params
                                 )
            server.server_info()
            connected = True
        except Exception:
            connected = False
        return connected
