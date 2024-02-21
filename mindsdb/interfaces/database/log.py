from abc import ABC, abstractmethod
from typing import List
from collections import OrderedDict

import pandas as pd

from mindsdb_sql import parse_sql
from mindsdb_sql.parser.ast import Select, Identifier, Star, BinaryOperation, Constant, Join
from mindsdb_sql.parser.utils import JoinType
from mindsdb_sql.render.sqlalchemy_render import SqlalchemyRender
from mindsdb_sql.planner.utils import query_traversal

from mindsdb.utilities.functions import resolve_table_identifier
from mindsdb.api.executor.utilities.sql import get_query_tables
from mindsdb.utilities.exception import EntityNotExistsError
import mindsdb.interfaces.storage.db as db
from mindsdb.utilities.context import context as ctx


class LogTable(ABC):
    name: str
    deletable: bool = False
    visible: bool = True
    kind: str = 'table'

    @staticmethod
    @abstractmethod
    def _get_base() -> Select:
        pass


class LLMLogTable(LogTable):
    name = 'llm_log'

    columns = [
        'API_KEY', 'MODEL_NAME', 'INPUT', 'OUTPUT', 'START_TIME', 'END_TIME',
        'PROMPT_TOKENS', 'COMPLETION_TOKENS', 'TOTAL_TOKENS', 'SUCCESS'
    ]

    types_map = {
        'SUCCESS': 'boolean',
        'START_TIME': 'datetime64[ns]',
        'END_TIME': 'datetime64[ns]'
    }

    @staticmethod
    def _get_base():
        query = Select(
            targets=[
                Identifier('llm_log.api_key', alias=Identifier('api_key')),
                Identifier('predictor.name', alias=Identifier('model_name')),
                Identifier('llm_log.input', alias=Identifier('input')),
                Identifier('llm_log.output', alias=Identifier('output')),
                Identifier('llm_log.start_time', alias=Identifier('start_time')),
                Identifier('llm_log.end_time', alias=Identifier('end_time')),
                Identifier('llm_log.prompt_tokens', alias=Identifier('prompt_tokens')),
                Identifier('llm_log.completion_tokens', alias=Identifier('completion_tokens')),
                Identifier('llm_log.total_tokens', alias=Identifier('total_tokens')),
                Identifier('llm_log.success', alias=Identifier('success'))
            ],
            from_table=Join(
                left=Identifier('llm_log'),
                right=Identifier('predictor'),
                join_type=JoinType.LEFT_JOIN,
                condition=BinaryOperation(
                    op='and',
                    args=(
                        BinaryOperation(
                            op='=',
                            args=(
                                Identifier('llm_log.company_id'),
                                Identifier('predictor.company_id')
                            )
                        ),
                        BinaryOperation(
                            op='=',
                            args=(
                                Identifier('llm_log.model_id'),
                                Identifier('predictor.id')
                            )
                        )
                    )
                )
            ),
            where=BinaryOperation(
                op='is' if ctx.company_id is None else '=',
                args=(Identifier('llm_log.company_id'), Constant(ctx.company_id))
            ),
            alias=Identifier('llm_log')
        )
        return query


class JobsHistoryTable(LogTable):
    name = 'jobs_history'

    columns = ['NAME', 'PROJECT', 'RUN_START', 'RUN_END', 'ERROR', 'QUERY']
    types_map = {
        'RUN_START': 'datetime64[ns]',
        'RUN_END': 'datetime64[ns]'
    }

    @staticmethod
    def _get_base():
        query = Select(
            targets=[
                Identifier('jobs.name', alias=Identifier('name')),
                Identifier('project.name', alias=Identifier('project')),
                Identifier('jobs_history.start_at', alias=Identifier('run_start')),
                Identifier('jobs_history.end_at', alias=Identifier('run_end')),
                Identifier('jobs_history.error', alias=Identifier('error')),
                Identifier('jobs_history.query_str', alias=Identifier('query'))
            ],
            from_table=Join(
                left=Join(
                    left=Identifier('jobs_history'),
                    right=Identifier('jobs'),
                    join_type=JoinType.LEFT_JOIN,
                    condition=BinaryOperation(
                        op='and',
                        args=(
                            BinaryOperation(
                                op='=',
                                args=(
                                    Identifier('jobs_history.company_id'),
                                    Identifier('jobs.company_id')
                                )
                            ),
                            BinaryOperation(
                                op='=',
                                args=(
                                    Identifier('jobs_history.job_id'),
                                    Identifier('jobs.id')
                                )
                            )
                        )
                    )
                ),
                right=Identifier('project'),
                join_type=JoinType.LEFT_JOIN,
                condition=BinaryOperation(
                    op='and',
                    args=(
                        BinaryOperation(
                            op='=',
                            args=(
                                Identifier('project.company_id'),
                                Identifier('jobs.company_id')
                            )
                        ),
                        BinaryOperation(
                            op='=',
                            args=(
                                Identifier('project.id'),
                                Identifier('jobs.project_id')
                            )
                        )
                    )
                )
            ),
            where=BinaryOperation(
                op='is' if ctx.company_id is None else '=',
                args=(Identifier('jobs_history.company_id'), Constant(ctx.company_id))
            ),
            alias=Identifier('jobs_history')
        )
        return query


class LogDBController:
    def __init__(self):
        self._tables = OrderedDict()
        self._tables['llm_log'] = LLMLogTable
        self._tables['jobs_history'] = JobsHistoryTable

    def get_list(self) -> List[LogTable]:
        return list(self._tables.values())

    def get(self, name: str = None) -> LogTable:
        try:
            return self._tables[name]
        except KeyError:
            raise EntityNotExistsError(f'Table log.{name} does not exists')

    def get_tables(self) -> OrderedDict:
        return self._tables

    def query(self, query: Select = None, native_query: str = None, session=None):
        if native_query is not None:
            if query is not None:
                raise Exception("'query' and 'native_query' arguments can not be used together")
            query = parse_sql(native_query)

        if type(query) is not Select:
            raise Exception("Only 'SELECT' is allowed for tables in log database")
        tables = get_query_tables(query)
        if len(tables) != 1:
            raise Exception("Only one table may be in query to log database")
        table = tables[0]
        if table[0] is not None and table[0].lower() != 'log':
            raise Exception("This is not a query to the log database")
        if table[1].lower() not in self._tables.keys():
            raise Exception(f"There is no table '{table[1]}' in the log database")

        log_table = self._tables[table[1].lower()]

        # region check that only allowed identifiers are used in the query
        available_columns_names = [column.lower() for column in log_table.columns]

        def check_columns(node, is_table, **kwargs):
            # region replace * to available columns
            if type(node) is Select:
                new_targets = []
                for target in node.targets:
                    if type(target) is Star:
                        new_targets += [Identifier(name) for name in available_columns_names]
                    else:
                        new_targets.append(target)
                node.targets = new_targets
            # endregion

            if type(node) is Identifier and is_table is False:
                parts = resolve_table_identifier(node)
                if parts[0] is not None and parts[0].lower() != 'llm_log':
                    raise Exception(f"Table '{parts[0]}' can not be used in query")
                if parts[1].lower() not in available_columns_names:
                    raise Exception(f"Column '{parts[1]}' can not be used in query")

        query_traversal(query, check_columns)
        # endregion

        query.from_table = log_table._get_base()

        render_engine = db.engine.name
        if render_engine == "postgresql":
            'postgres'
        render = SqlalchemyRender(render_engine)
        query_str = render.get_string(query, with_failback=False)
        df = pd.read_sql_query(query_str, db.engine)

        # region cast columns values to proper types
        for column_name, column_type in log_table.types_map.items():
            for df_column_name in df.columns:
                if df_column_name.lower() == column_name.lower() and df[df_column_name].dtype != column_type:
                    df[df_column_name] = df[df_column_name].astype(column_type)
        # endregion

        columns_info = [{
            'name': k,
            'type': v
        } for k, v in df.dtypes.items()]

        return df.to_dict(orient='split')['data'], columns_info
