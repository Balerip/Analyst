import sys
import os
import pickle
import subprocess
from collections import OrderedDict

from mindsdb.utilities.config import Config
from mindsdb.integrations.libs.const import HANDLER_CONNECTION_ARG_TYPE as ARG_TYPE
from mindsdb.integrations.libs.base import BaseMLEngine
from pandas.api import types as pd_types
import numpy as np


class BYOMHandler(BaseMLEngine):

    name = 'byom'

    def _run_command(self, params):
        params_enc = pickle.dumps(params)

        # TODO change to virtualenv from config
        python_path = sys.executable
        wrapper_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'proc_wrapper.py')
        p = subprocess.Popen(
            [python_path, wrapper_path],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
        )

        p.stdin.write(params_enc)
        p.stdin.close()
        ret_enc = p.stdout.read()

        p.wait()

        try:
            ret = pickle.loads(ret_enc)
        except (pickle.UnpicklingError, EOFError):
            raise RuntimeError(p.stderr.read())
        return ret

    def _get_model_code(self):
        # TODO :
        file_name = self.engine_storage.get_connection_args()['model_code']
        return self.engine_storage.file_get(file_name)

    def create(self, target, df=None, args=None, **kwargs):
        is_cloud = Config().get('cloud', False)
        if is_cloud is True:
            raise RuntimeError('BYOM is disabled on cloud')

        params = {
            'method': 'train',
            'df': df,
            'code': self._get_model_code(),
            'to_predict': target
        }

        model_params = self._run_command(params)
        encoded = pickle.dumps(model_params)
        self.model_storage.file_set('model', encoded)

        # TODO return columns?

        def convert_type(field_type):
            if pd_types.is_integer_dtype(field_type):
                return 'integer'
            elif pd_types.is_numeric_dtype(field_type):
                return 'float'
            elif pd_types.is_datetime64_any_dtype(field_type):
                return 'datetime'
            else:
                return 'categorical'

        columns = {
            target: convert_type(np.object)
        }

        self.model_storage.columns_set(columns)

    def predict(self, df, args=None):
        encoded = self.model_storage.file_get('model')
        model_params = pickle.loads(encoded)
        params = {
            'method': 'predict',
            'code': self._get_model_code(),
            'df': df,
            'model': model_params,
        }
        pred_df = self._run_command(params)

        # rename target column
        # target = self.model_storage.get_info()['to_predict'][0]
        # pred_df = pred_df.rename(columns={target: 'prediction'})
        return pred_df


connection_args = OrderedDict(
    model_code={
        'type': ARG_TYPE.PATH,
        'description': 'The path name to model code'
    }
)