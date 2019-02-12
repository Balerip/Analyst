"""
*******************************************************
 * Copyright (C) 2017 MindsDB Inc. <copyright@mindsdb.com>
 *
 * This file is part of MindsDB Server.
 *
 * MindsDB Server can not be copied and/or distributed without the express
 * permission of MindsDB Inc
 *******************************************************
"""


import copy
import numpy as np
import itertools
from mindsdb.libs.data_types.mindsdb_logger import log
import traceback

from mindsdb.libs.constants.mindsdb import *
from mindsdb.libs.phases.base_module import BaseModule
from collections import OrderedDict
from mindsdb.libs.helpers.norm_denorm_helpers import norm, norm_buckets
from mindsdb.libs.helpers.text_helpers import hashtext, clean_float, cast_string_to_python_type
from mindsdb.libs.data_types.transaction_metadata import TransactionMetadata


class DataVectorizer(BaseModule):

    phase_name = PHASE_DATA_VECTORIZATION


    def run(self):

        column_stats = self.transaction.persistent_model_metadata.column_stats
        # this is a template of how we store columns
        column_packs_template = OrderedDict()
        # create a template of the column packs
        for i, column_name in enumerate(self.transaction.input_data.columns):
            column_packs_template[column_name] = []

        if self.transaction.metadata.type == TRANSACTION_LEARN:
            subsets = [
                {
                    'name': 'test',
                    'subset_pointer': self.transaction.model_data.test_set,
                    'map': self.transaction.model_data.test_set_map,
                    'indexes': self.transaction.input_data.test_indexes
                },
                {
                    'name': 'train',
                    'subset_pointer': self.transaction.model_data.train_set,
                    'map': self.transaction.model_data.train_set_map,
                    'indexes': self.transaction.input_data.train_indexes
                },
                {
                    'name': 'validation',
                    'subset_pointer': self.transaction.model_data.validation_set,
                    'map': self.transaction.model_data.validation_set_map,
                    'indexes': self.transaction.input_data.validation_indexes
                }
            ]
        else:
            subsets = [
                {
                    'name': 'predict',
                    'subset_pointer': self.transaction.model_data.predict_set,
                    'map': self.transaction.model_data.predict_set_map,
                    'indexes': self.transaction.input_data.all_indexes
                }
            ]

        # iterate over all groups and populate tensors by columns

        for subset in subsets:

            subset_pointer = subset['subset_pointer'] # for ease use a pointer

            # iterate over all indexes that belong to this subset
            for subset_group_by_hash in subset['indexes']:

                subset_pointer[subset_group_by_hash] = copy.deepcopy(column_packs_template)

                for input_row_index in subset['indexes'][subset_group_by_hash]:
                    row = self.transaction.input_data.data_array[input_row_index]  # extract the row from input data
                    for column_name in subset_pointer[subset_group_by_hash]:
                        column_index = self.transaction.input_data.columns.index(column_name)
                        cell_value = row[column_index]
                        value = cast_string_to_python_type(cell_value)
                        normalized_value = norm(value=value, cell_stats=column_stats[column_name])  # this should return a vector representation already normalized
                        subset_pointer[subset_group_by_hash][column_name] += [normalized_value]


        return []


def test():
    from mindsdb.libs.controllers.mindsdb_controller import MindsDBController as MindsDB

    mdb = MindsDB()

    # We tell mindsDB what we want to learn and from what data
    mdb.learn(
        from_data="https://raw.githubusercontent.com/mindsdb/mindsdb/master/docs/examples/basic/home_rentals.csv",
        # the path to the file where we can learn from, (note: can be url)
        predict='rental_price',  # the column we want to learn to predict given all the data in the file
        model_name='home_rentals',  # the name of this model
        breakpoint=PHASE_DATA_VECTORIZATION
    )



# only run the test if this file is called from debugger
if __name__ == "__main__":
    test()
