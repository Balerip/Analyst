from mindsdb.libs.helpers.general_helpers import convert_snake_to_cammelcase_string
from mindsdb.libs.constants.mindsdb import *
from mindsdb.libs.phases.base_module import BaseModule
from mindsdb.libs.data_types.sampler import Sampler
from mindsdb.libs.ml_models.pytorch.libs import base_model;
from mindsdb.libs.ml_models.probabilistic_validator import ProbabilisticValidator
from mindsdb.libs.ml_models.pytorch.libs.torch_helpers import array_to_float_variable

import pandas as pd

class ModelAnalyzer(BaseModule):

    phase_name = PHASE_MODEL_ANALYZER

    def run(self):
        #for group in self.transaction.model_data.validation_set:
        #columns = self.transaction.model_data.validation_set[group]

        validation_sampler = Sampler(self.transaction.model_data.validation_set, metadata_as_stored=self.transaction.persistent_model_metadata,
                                    ignore_types=self.transaction.data_model_object.ignore_types, sampler_mode=SAMPLER_MODES.LEARN)

        validation_sampler.variable_wrapper = array_to_float_variable
        '''
        @ <--- field ids is not yet set at this point
        bm = base_model.BaseModel(validation_sampler.getSampleBatch())
        self.data_model_object = bm.load_from_disk(file_ids=self.transaction.persistent_ml_model_info.fs_file_ids)
        '''

        probabilistic_validator = ProbabilisticValidator()


        predictions = self.transaction.data_model_object.testModel(validation_sampler)
        print(predictions.error)
        print(predictions.accuracy)
        print(predictions.predicted_targets)
        print(predictions.real_targets)
        exit()
        for col in predictions:
            for i in range(predictions[col]):
                predicted = predictions[col][i]
                real = real_values[i]
                features = features_arr[i]
                register_observation(features, real, predicted)


def test():
    from mindsdb.libs.controllers.predictor import Predictor
    from mindsdb import CONFIG

    CONFIG.DEBUG_BREAK_POINT = PHASE_MODEL_ANALYZER

    mdb = Predictor(name='home_rentals')

    mdb.learn(
        from_data="https://raw.githubusercontent.com/mindsdb/mindsdb/master/docs/examples/basic/home_rentals.csv",
        # the path to the file where we can learn from, (note: can be url)
        to_predict='rental_price',  # the column we want to learn to predict given all the data in the file
        sample_margin_of_error=0.02,
        stop_training_in_x_seconds=3
    )



# only run the test if this file is called from debugger
if __name__ == "__main__":
    test()
