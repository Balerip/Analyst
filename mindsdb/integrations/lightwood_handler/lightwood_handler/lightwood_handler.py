import dill
import pandas as pd
from typing import Dict, List, Optional

import sqlalchemy

from utils import unpack_jsonai_old_args, get_aliased_columns, _recur_get_conditionals, load_predictor

import lightwood
from lightwood.api.types import JsonAI
from lightwood.api.high_level import json_ai_from_problem, predictor_from_code, code_from_json_ai, ProblemDefinition

from utils import unpack_jsonai_old_args, get_aliased_columns, _recur_get_conditionals, load_predictor
from utils import default_train_data_gather
from join_utils import get_ts_join_input, get_join_input
from mindsdb.integrations.libs.base_handler import BaseHandler, PredictiveHandler
from mindsdb.integrations.libs.storage_handler import SqliteStorageHandler
from mindsdb.integrations.mysql_handler.mysql_handler import MySQLHandler
from mindsdb.interfaces.model.learn_process import brack_to_mod, rep_recur
from mindsdb.utilities.config import Config

from mindsdb_sql import parse_sql
from mindsdb_sql.parser.ast import Join, BinaryOperation, Identifier, Constant, Select, OrderBy
from mindsdb_sql.parser.dialects.mindsdb import (
    RetrainPredictor,
    CreatePredictor,
    DropPredictor
)


class LightwoodHandler(PredictiveHandler):
    def __init__(self, name):
        """ Lightwood AutoML integration """  # noqa
        super().__init__(name)
        self.storage = None
        self.parser = parse_sql
        self.dialect = 'mindsdb'
        self.handler_dialect = 'mysql'

        self.lw_dtypes_to_sql = {
            "integer": sqlalchemy.Integer,
            "float": sqlalchemy.Float,
            "quantity": sqlalchemy.Float,
            "binary": sqlalchemy.Text,
            "categorical": sqlalchemy.Text,
            "tags": sqlalchemy.Text,
            "date": sqlalchemy.DateTime,
            "datetime": sqlalchemy.DateTime,
            "short_text": sqlalchemy.Text,
            "rich_text": sqlalchemy.Text,
            "num_array": sqlalchemy.Text,
            "cat_array": sqlalchemy.Text,
            "num_tsarray": sqlalchemy.Text,
            "cat_tsarray": sqlalchemy.Text,
            "empty": sqlalchemy.Text,
            "invalid": sqlalchemy.Text,
        }  # image, audio, video not supported
        self.lw_dtypes_overrides = {
            'original_index': sqlalchemy.Integer,
            'confidence': sqlalchemy.Float,
            'lower': sqlalchemy.Float,
            'upper': sqlalchemy.Float
        }

    def connect(self, **kwargs) -> Dict[str, int]:
        """ Setup storage handler and check lightwood version """  # noqa
        self.storage = SqliteStorageHandler(context=self.name, config=kwargs['config'])  # TODO non-KV storage handler
        return self.check_status()

    def check_status(self) -> Dict[str, int]:
        try:
            import lightwood
            year, major, minor, hotfix = lightwood.__version__.split('.')
            assert int(year) > 22 or (int(year) == 22 and int(major) >= 4)
            print("Lightwood OK!")
            return {'status': '200'}
        except AssertionError as e:
            print("Cannot import lightwood!")
            return {'status': '503', 'error': e}

    def get_tables(self) -> List:
        """ Returns list of model names (that have been succesfully linked with CREATE PREDICTOR) """  # noqa
        models = self.storage.get('models')
        return list(models.keys()) if models else []

    def describe_table(self, table_name: str) -> Dict:
        """ For getting standard info about a table. e.g. data types """  # noqa
        if table_name not in self.get_tables():
            print("Table not found.")
            return {}
        return self.storage.get('models')[model_name]['jsonai']

    def native_query(self, query: str) -> Optional[object]:
        statement = self.parser(query, dialect=self.dialect)

        if type(statement) == CreatePredictor:
            model_name = statement.name.parts[-1]

            if model_name in self.get_tables():
                raise Exception("Error: this model already exists!")

            target = statement.targets[0].parts[-1]
            params = { 'target': target }
            if statement.order_by:
                params['timeseries_settings'] = {
                    'is_timeseries': True,
                    'order_by': [str(col) for col in statement.order_by],
                    'group_by': [str(col) for col in statement.group_by],
                    'window': int(statement.window),
                    'horizon': int(statement.horizon),
                }

            json_ai_override = statement.using if statement.using else {}
            unpack_jsonai_old_args(json_ai_override)

            # get training data from other integration
            handler = MDB_CURRENT_HANDLERS[str(statement.integration_name)]  # TODO import from mindsdb init
            handler_query = self.parser(statement.query_str, dialect=self.handler_dialect)
            df = default_train_data_gather(handler, handler_query)

            json_ai_keys = list(lightwood.JsonAI.__dict__['__annotations__'].keys())
            json_ai = json_ai_from_problem(df, ProblemDefinition.from_dict(params)).to_dict()
            json_ai_override = brack_to_mod(json_ai_override)
            rep_recur(json_ai, json_ai_override)
            json_ai = JsonAI.from_dict(json_ai)

            code = code_from_json_ai(json_ai)
            predictor = predictor_from_code(code)
            predictor.learn(df)

            all_models = self.storage.get('models')
            serialized_predictor = dill.dumps(predictor)
            payload = {
                'code': code,
                'jsonai': json_ai,
                'stmt': statement,
                'predictor': serialized_predictor,
            }
            if all_models is not None:
                all_models[model_name] = payload
            else:
                all_models = {model_name: payload}
            self.storage.set('models', all_models)

        elif type(statement) == RetrainPredictor:
            model_name = statement.name.parts[-1]
            if model_name not in self.get_tables():
                raise Exception("Error: this model does not exist, so it can't be retrained. Train a model first.")

            all_models = self.storage.get('models')
            original_stmt = all_models[model_name]['stmt']

            handler = MDB_CURRENT_HANDLERS[str(original_stmt.integration_name)]  # TODO import from mindsdb init
            handler_query = self.parser(original_stmt.query_str, dialect=self.handler_dialect)
            df = default_train_data_gather(handler, handler_query)

            predictor = load_predictor(all_models[model_name], model_name)
            predictor.adjust(df)
            all_models[model_name]['predictor'] = dill.dumps(predictor)
            self.storage.set('models', all_models)

        elif type(statement) == DropPredictor:
            to_drop = statement.name.parts[-1]
            all_models = self.storage.get('models')
            del all_models[to_drop]
            self.storage.set('models', all_models)

        else:
            raise Exception(f"Query type {type(statement)} not supported")

    def query(self, query) -> dict:
        model_name, _, _ = self._get_model_name(query)
        model = self._get_model(model_name)
        values = _recur_get_conditionals(query.where.args, {})
        df = pd.DataFrame.from_dict(values)
        df = self._call_predictor(df, model)
        return {'data_frame': df}

    def join(self, stmt, data_handler: BaseHandler, into: Optional[str] = None) -> pd.DataFrame:
        """
        Batch prediction using the output of a query passed to a data handler as input for the model.
        """  # noqa
        model_name, model_alias, model_side = self._get_model_name(stmt)
        data_side = 'right' if model_side == 'left' else 'left'
        model = self._get_model(model_name)
        is_ts = model.problem_definition.timeseries_settings.is_timeseries

        if not is_ts:
            model_input = get_join_input(stmt, model, data_handler, data_side)
        else:
            model_input = get_ts_join_input(stmt, model, data_handler, data_side)

        # get model output and rename columns
        predictions = self._call_predictor(model_input, model)
        model_input.columns = get_aliased_columns(list(model_input.columns), model_alias, stmt.targets, mode='input')
        predictions.columns = get_aliased_columns(list(predictions.columns), model_alias, stmt.targets, mode='output')

        if into:
            try:
                dtypes = {}
                for col in predictions.columns:
                    if model.dtype_dict.get(col, False):
                        dtypes[col] = self.lw_dtypes_to_sql.get(col, sqlalchemy.Text)
                    else:
                        dtypes[col] = self.lw_dtypes_overrides.get(col, sqlalchemy.Text)

                data_handler.select_into(into, predictions, dtypes=dtypes)
            except Exception as e:
                print("Error when trying to store the JOIN output in data handler.")

        return predictions

    def _get_model_name(self, stmt):
        side = None
        models = self.get_tables()
        if type(stmt.from_table) == Join:
            model_name = stmt.from_table.right.parts[-1]
            side = 'right'
            if model_name not in models:
                model_name = stmt.from_table.left.parts[-1]
                side = 'left'
            alias = str(getattr(stmt.from_table, side).alias)
        else:
            model_name = stmt.from_table.parts[-1]
            alias = None  # todo: fix this

        if model_name not in models:
            raise Exception("Error, not found. Please create this predictor first.")

        return model_name, alias, side

    def _get_model(self, model_name):
        predictor_dict = self._get_model_info(model_name)
        predictor = load_predictor(predictor_dict, model_name)
        return predictor

    def _get_model_info(self, model_name):
        """ Returns a dictionary with three keys: 'jsonai', 'predictor' (serialized), and 'code'. """  # noqa
        return self.storage.get('models')[model_name]

    def _call_predictor(self, df, predictor):
        predictions = predictor.predict(df)
        if 'original_index' in predictions.columns:
            predictions = predictions.sort_values(by='original_index')
        return df.join(predictions)


if __name__ == '__main__':
    from lightwood.mixer import LightGBM
    # TODO: turn this into tests

    data_handler_name = 'mysql_handler'
    # todo: MDB needs to expose all available handlers through some sort of global state DB
    # todo: change data gathering logic if task is TS, use self._data_gather or similar
    # todo: eventually we would maybe do `from mindsdb.handlers import MDB_CURRENT_HANDLERS` registry
    MDB_CURRENT_HANDLERS = {
        data_handler_name: MySQLHandler('test_handler', **{
            "host": "localhost",
            "port": "3306",
            "user": "root",
            "password": "root",
            "database": "test",
            "ssl": False
        })
    }  # todo: handler CRUD should be done at mindsdb top-level
    data_handler = MDB_CURRENT_HANDLERS[data_handler_name]
    print(data_handler.check_status())

    cls = LightwoodHandler('LWtest')
    config = Config()
    print(cls.connect(config={'path': config['paths']['root'], 'name': 'lightwood_handler.db'}))

    model_name = 'lw_test_predictor'
    # try:
    #     print('dropping predictor...')
    #     cls.native_query(f"DROP PREDICTOR {model_name}")
    # except:
    #     print('failed to drop')
    #     pass

    print(cls.get_tables())

    data_table_name = 'home_rentals_subset'
    target = 'rental_price'
    if model_name not in cls.get_tables():
        query = f"CREATE PREDICTOR {model_name} FROM {data_handler_name} (SELECT * FROM test.{data_table_name}) PREDICT {target}"
        cls.native_query(query)

        query = f"RETRAIN {model_name}"  # try retrain syntax
        cls.native_query(query)

    print(cls.describe_table(f'{model_name}'))

    # try single WHERE condition
    query = f"SELECT target from {model_name} WHERE sqft=100"
    parsed = cls.parser(query, dialect=cls.dialect)
    predicted = cls.query(parsed)['data_frame']

    # try multiple
    query = f"SELECT target from {model_name} WHERE sqft=100 AND number_of_rooms=2 AND number_of_bathrooms=1"
    parsed = cls.parser(query, dialect=cls.dialect)
    predicted = cls.query(parsed)['data_frame']

    into_table = 'test_join_into_lw'
    query = f"SELECT tb.{target} as predicted, ta.{target} as truth, ta.sqft from {data_handler_name}.{data_table_name} AS ta JOIN {model_name} AS tb LIMIT 10"
    parsed = cls.parser(query, dialect=cls.dialect)
    predicted = cls.join(parsed, data_handler, into=into_table)

    # checks whether `into` kwarg does insert into the table or not
    q = f"SELECT * FROM {into_table}"
    qp = cls.parser(q, dialect='mysql')
    assert len(data_handler.query(qp)['data_frame']) > 0

    # try:
    #     data_handler.native_query(f"DROP TABLE test.{into_table}")
    # except:
    #     pass

    # try:
    #     cls.native_query(f"DROP PREDICTOR {model_name}")
    # except:
    #     pass

    # Test 2: add custom JsonAi
    model_name = 'lw_test_predictor2'
    # try:
    #     cls.native_query(f"DROP PREDICTOR {model_name}")
    # except:
    #     pass

    if model_name not in cls.get_tables():
        using_str = 'model.args={"submodels": [{"module": "LightGBM", "args": {"stop_after": 12, "fit_on_dev": True}}]}'
        query = f'CREATE PREDICTOR {model_name} FROM {data_handler_name} (SELECT * FROM test.{data_table_name}) PREDICT {target} USING {using_str}'
        cls.native_query(query)

    m = load_predictor(cls.storage.get('models')[model_name], model_name)
    assert len(m.ensemble.mixers) == 1
    assert isinstance(m.ensemble.mixers[0], LightGBM)

    # Timeseries predictor
    model_name = 'lw_test_predictor3'
    target = 'Traffic'
    data_table_name = 'arrival'
    oby = 'T'
    gby = 'Country'
    window = 8
    horizon = 4

    model_name = 'lw_test_predictor3'
    # try:
    #     cls.native_query(f"DROP PREDICTOR {model_name}")
    # except:
    #     pass

    if model_name not in cls.get_tables():
        query = f'CREATE PREDICTOR {model_name} FROM {data_handler_name} (SELECT * FROM test.{data_table_name}) PREDICT {target} ORDER BY {oby} GROUP BY {gby} WINDOW {window} HORIZON {horizon}'
        cls.native_query(query)

    p = cls.storage.get('models')
    m = load_predictor(p[model_name], model_name)
    assert m.problem_definition.timeseries_settings.is_timeseries

    # get predictions from a time series model
    into_table = 'test_join_tsmodel_into_lw'
    query = f"SELECT tb.{target} as predicted, ta.{target} as truth, ta.{oby} from {data_handler_name}.{data_table_name} AS ta JOIN mindsdb.{model_name} AS tb ON 1=1 WHERE ta.{oby} > LATEST LIMIT 10"
    parsed = cls.parser(query, dialect=cls.dialect)
    predicted = cls.join(parsed, data_handler, into=into_table)

    # try:
    #     data_handler.native_query(f"DROP TABLE {into_table}")
    # except Exception as e:
    #     print(e)

    # TODO: bring all train+predict queries in mindsdb_sql test suite
