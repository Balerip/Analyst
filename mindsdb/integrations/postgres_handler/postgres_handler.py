from contextlib import closing

import psycopg
from psycopg.pq import ExecStatus
from pandas import DataFrame

from mindsdb_sql import parse_sql
from mindsdb_sql.render.sqlalchemy_render import SqlalchemyRender

from mindsdb.integrations.libs.base_handler import DatabaseHandler
from mindsdb.api.mysql.mysql_proxy.libs.constants.response_type import RESPONSE_TYPE
from mindsdb.utilities.log import log
from mindsdb.api.mysql.mysql_proxy.datahub.classes.tables_row import TablesRow, TABLES_ROW_TYPE


class PostgresHandler(DatabaseHandler):
    """
    This handler handles connection and execution of the PostgreSQL statements.
    """
    type = 'postgres'

    def __init__(self, name=None, **kwargs):
        super().__init__(name)
        self.parser = parse_sql
        self.connection_args = kwargs.get('connection_data')
        self.dialect = 'postgresql'
        self.database = self.connection_args.get('database')
        del self.connection_args['database']
        self.renderer = SqlalchemyRender('postgres')

    def __connect(self):
        """
        Handles the connection to a PostgreSQL database insance.
        """
        # TODO: Check psycopg_pool
        self.connection_args['dbname'] = self.database
        args = self.connection_args.copy()
        del args['type']
        del args['publish']
        del args['test']
        # del args['dbname']
        del args['date_last_update']
        del args['integrations_name']
        del args['database_name']
        del args['id']
        connection = psycopg.connect(**args, connect_timeout=10)
        return connection

    # TODO check_connection ?
    def check_status(self):
        """
        Check the connection of the PostgreSQL database
        :return: success status and error message if error occurs
        """
        status = {
            'success': False
        }
        try:
            con = self.__connect()
            with closing(con) as con:
                with con.cursor() as cur:
                    cur.execute('select 1;')
            status['success'] = True
        except psycopg.Error as e:
            log.error(f'Error connecting to PostgreSQL {self.database}, {e}!')
            status['error'] = e
        return status

    def native_query(self, query):
        """
        Receive SQL query and runs it
        :param query: The SQL query to run in PostgreSQL
        :return: returns the records from the current recordset
        """
        con = self.__connect()
        with closing(con) as con:
            with con.cursor() as cur:
                try:
                    cur.execute(query)
                    if ExecStatus(cur.pgresult.status) == ExecStatus.COMMAND_OK:
                        response = {
                            'type': RESPONSE_TYPE.OK
                        }
                    else:
                        result = cur.fetchall()
                        response = {
                            'type': RESPONSE_TYPE.TABLE,
                            'data_frame': DataFrame(
                                result,
                                columns=[x.name for x in cur.description]
                            )
                        }
                except Exception as e:
                    log.error(f'Error running query: {query} on {self.database}!')
                    response = {
                        'type': RESPONSE_TYPE.ERROR,
                        'error_code': 0,
                        'error_message': str(e)
                    }
        return response

    def query(self, query):
        """
        Retrieve the data from the SQL statement with eliminated rows that dont satisfy the WHERE condition
        """
        query_str = self.renderer.get_string(query, with_failback=True)
        return self.native_query(query_str)

    def get_tables(self):
        """
        List all tabels in PostgreSQL without the system tables information_schema and pg_catalog
        """
        query = """
            SELECT
                table_schema,
                table_name
            FROM
                information_schema.tables
            WHERE
                table_schema NOT IN ('information_schema', 'pg_catalog')
                and table_type = 'BASE TABLE'
        """
        result = self.native_query(query)
        result['data'] = [
            TablesRow(TABLE_SCHEMA=row[0], TABLE_NAME=row[1])
            for row in result['data_frame'].to_numpy()
        ]
        return result

    # def get_views(self):
    #     """
    #     List all views in PostgreSQL without the system views information_schema and pg_catalog
    #     """
    #     query = "SELECT * FROM information_schema.views WHERE table_schema NOT IN ('information_schema', 'pg_catalog')"
    #     result = self.native_query(query)
    #     return result

    # def describe_table(self, table_name):
    #     """
    #     List names and data types about the table coulmns
    #     """
    #     query = f"SELECT table_name, column_name, data_type FROM \
    #           information_schema.columns WHERE table_name='{table_name}';"
    #     result = self.native_query(query)
    #     return result

# response = {
#     'type': RESPONSE_TYPE.ERROR,
#     'error_code': 0,
#     'error_message': str(e)
# }


# class SQLAnswer:
#     def __init__(self, resp_type: RESPONSE_TYPE, columns: List[Dict] = None, data: List[Dict] = None,
#                  status: int = None, state_track: List[List] = None, error_code: int = None, error_message: str = None):
#         self.resp_type = resp_type
#         self.columns = columns
#         self.data = data
#         self.status = status
#         self.state_track = state_track
#         self.error_code = error_code
#         self.error_message = error_message

#     @property
#     def type(self):
#         return self.resp_type

# class HandlerResponse:
    