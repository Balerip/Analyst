import os
import shutil
import importlib
import json
import sys

import mindsdb_native
import pandas as pd

from mindsdb.interfaces.database.database import DatabaseWrapper
from mindsdb.interfaces.native.mindsdb import MindsdbNative
from mindsdb.utilities.fs import get_or_create_dir_struct

class CustomModels():
    def __init__(self, config):
        self.config = config
        self.dbw = DatabaseWrapper(self.config)
        _, _, _, self.storage_dir = get_or_create_dir_struct()
        self.model_cache = {}
        self.mindsdb_native = MindsdbNative(self.config)
        self.dbw = DatabaseWrapper(self.config)

    def _dir(self, name):
        return str(os.path.join(self.storage_dir, 'custom_model_' + name))

    def _internal_load(self, name):

        if name in self.model_cache:
            return self.model_cache[name]

        #spec = importlib.util.spec_from_file_location(name, self._dir(name) + '/model.py')
        #module = importlib.util.module_from_spec(spec)
        #spec.loader.exec_module(module)
        sys.path.insert(0, self._dir(name))
        module = __import__(name)

        try:
            model = module.Model.load(os.path.join(self._dir(name), 'model.pickle'))
        except:
            model = module.Model()
            if hasattr(model, 'setup'):
                model.setup()

        self.model_cache[name] = model

        return model

    def learn(self, name, from_data, to_predict, kwargs={}):
        data_source = getattr(mindsdb_native, from_data['class'])(*from_data['args'], **from_data['kwargs'])
        data_frame = data_source._df
        model = self._internal_load(name)

        data_analysis = self.mindsdb_native.analyse_dataset(data_source)['data_analysis_v2']

        with open(os.path.join(self._dir(name), 'metadata.json'), 'w') as fp:
            json.dump({
                'name': name
                ,'data_analysis': data_analysis
                ,'predict': to_predict if isinstance(to_predict,list) else [to_predict]
            }, fp)

        model.fit(data_frame, to_predict, data_analysis, kwargs)

        model.save(os.path.join(self._dir(name), 'model.pickle'))

        self.dbw.register_predictors([self.get_model_data(name)])

    def predict(self, name, when_data=None, from_data=None, kwargs={}):
        if from_data is not None:
            data_source = getattr(mindsdb_native, from_data['class'])(*from_data['args'], **from_data['kwargs'])
            data_frame = data_source._df
        elif when_data is not None:
            if isinstance(when_data, dict):
                for k in when_data: when_data[k] = [when_data[k]]
                data_frame = pd.DataFrame(when_data)
            else:
                data_frame = when_data

        model = self._internal_load(name)
        predictions = model.predict(data_frame, kwargs)

        pred_arr = []
        for i in range(len(predictions)):
            pred_arr.append({})
            pred_arr[-1] = {}
            for col in predictions.columns:
                pred_arr[-1][col] = {}
                pred_arr[-1][col]['predicted_value'] = predictions[col].iloc[i]

        return pred_arr

    def get_model_data(self, name):
        with open(os.path.join(self._dir(name), 'metadata.json'), 'r') as fp:
            return json.load(fp)

    def get_models(self, status='any'):
        models = []
        for model_dir in os.listdir(self.storage_dir):
            if 'custom_model_' in model_dir:
                name = model_dir.replace('custom_model_','')
                try:
                    models.append(self.get_model_data(name))
                except:
                    print(f'Model {name} not found !')

        return models

    def delete_model(self, name):
        shutil.rmtree(self._dir(name))
        self.dbw.unregister_predictor(name)

    def rename_model(self, name, new_name):
        shutil.move(self._dir(name), self._dir(new_name))

    def load_model(self, fpath, name):
        shutil.unpack_archive(fpath, self._dir(name), 'zip')
        shutil.move( os.path.join(self._dir(name), 'model.py') ,  os.path.join(self._dir(name), f'{name}.py') )
        with open(os.path.join(self._dir(name), 'metadata.json') , 'w') as fp:
            json.dump({
                'name': name
                ,'data_analysis': {
                    'Empty_target': {
                        'typing': {
                            'data_type': 'Text'
                            ,'data_subtype': 'Short Text'
                        }
                    }
                    ,'Empty_input': {
                        'typing': {
                            'data_type': 'Text'
                            ,'data_subtype': 'Short Text'
                        }
                    }
                }
                ,'predict': ['Empty_target']
            }, fp)

        with open(os.path.join(self._dir(name), '__init__.py') , 'w') as fp:
            fp.write('')

        self.dbw.register_predictors([self.get_model_data(name)])
