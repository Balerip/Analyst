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

import random
import warnings
from mindsdb.libs.data_types.mindsdb_logger import log

import numpy as np
import scipy.stats as st
from dateutil.parser import parse as parseDate
from sklearn.ensemble import IsolationForest

import mindsdb.config as CONFIG

from mindsdb.libs.constants.mindsdb import *
from mindsdb.libs.phases.base_module import BaseModule
from mindsdb.libs.helpers.text_helpers import splitRecursive, cleanfloat, tryCastToNumber
from mindsdb.external_libs.stats import calculate_sample_size

from mindsdb.libs.data_types.transaction_metadata import TransactionMetadata


class StatsGenerator(BaseModule):

    phase_name = PHASE_STATS_GENERATOR

    def isNumber(self, string):
        """ Returns True if string is a number. """
        try:
            cleanfloat(string)
            return True
        except ValueError:
            return False

    def isDate(self, string):
        """ Returns True if string is a valid date format """
        try:
            parseDate(string)
            return True
        except ValueError:
            return False

    def getColumnDataType(self, data):
        """ Returns the column datatype based on a random sample of 15 elements """
        currentGuess = DATA_TYPES.NUMERIC
        type_dist = {}

        for element in data:
            if self.isNumber(element):
                currentGuess = DATA_TYPES.NUMERIC
            elif self.isDate(element):
                currentGuess = DATA_TYPES.DATE
            else:
                currentGuess = DATA_TYPES.CLASS

            if currentGuess not in type_dist:
                type_dist[currentGuess] = 1
            else:
                type_dist[currentGuess] += 1

        curr_data_type = DATA_TYPES.CLASS
        max_data_type = 0

        for data_type in type_dist:
            if type_dist[data_type] > max_data_type:
                curr_data_type = data_type
                max_data_type = type_dist[data_type]

        if curr_data_type == DATA_TYPES.CLASS:
            return self.getTextType(data), type_dist

        return curr_data_type, type_dist


    def getTextType(self, data):

        total_length = len(data)
        key_count = {}
        max_number_of_words = 0

        for cell in data:

            if cell not in key_count:
                key_count[cell] = 1
            else:
                key_count[cell] += 1

            cell_wseparator = cell
            sep_tag = '{#SEP#}'
            for separator in WORD_SEPARATORS:
                cell_wseparator = str(cell_wseparator).replace(separator,sep_tag)

            words_split = cell_wseparator.split(sep_tag)
            words = len([ word for word in words_split if word not in ['', None] ])

            if max_number_of_words < words:
                max_number_of_words += words

        if max_number_of_words == 1:
            return DATA_TYPES.CLASS
        if max_number_of_words <= 3 and len(key_count) < total_length * 0.8:
            return DATA_TYPES.CLASS
        else:
            return DATA_TYPES.FULL_TEXT



    def getWordsDictionary(self, data, full_text = False):
        """ Returns an array of all the words that appear in the dataset and the number of times each word appears in the dataset """

        splitter = lambda w, t: [wi.split(t) for wi in w] if type(w) == type([]) else splitter(w,t)

        if full_text:
            # get all words in every cell and then calculate histograms
            words = []
            for cell in data:
                words += splitRecursive(cell, WORD_SEPARATORS)

            hist = {i: words.count(i) for i in words}
            x = list(hist.keys())
            histogram = {
                'x': x,
                'y': list(hist.values())
            }
            return x, histogram


        else:
            hist = {i: data.count(i) for i in data}
            x = list(hist.keys())
            histogram = {
                'x': x,
                'y': list(hist.values())
            }
            return x, histogram

    def getParamsAsDictionary(self, params):
        """ Returns a dictionary with the params of the distribution """
        arg = params[:-2]
        loc = params[-2]
        scale = params[-1]
        ret = {
            'loc': loc,
            'scale': scale,
            'shape': arg
        }
        return ret



    def run(self):

        self.train_meta_data = TransactionMetadata()
        self.train_meta_data.setFromDict(self.transaction.persistent_model_metadata.train_metadata)

        header = self.transaction.input_data.columns
        non_null_data = {}

        for column in header:
            non_null_data[column] = []

        empty_count = {}
        column_count = {}

        # we dont need to generate statistic over all of the data, so we subsample, based on our accepted margin of error
        population_size = len(self.transaction.input_data.data_array)
        sample_size = int(calculate_sample_size(population_size=population_size, margin_error=CONFIG.DEFAULT_MARGIN_OF_ERROR, confidence_level=CONFIG.DEFAULT_CONFIDENCE_LEVEL))

        # get the indexes of randomly selected rows given the population size
        input_data_sample_indexes = random.sample(range(population_size), sample_size)
        self.log.info('population_size={population_size},  sample_size={sample_size}  {percent:.2f}%'.format(population_size=population_size, sample_size=sample_size, percent=(sample_size/population_size)*100))

        for sample_i in input_data_sample_indexes:
            row = self.transaction.input_data.data_array[sample_i]

            for i, val in enumerate(row):
                column = header[i]
                value = tryCastToNumber(val)
                if not column in empty_count:
                    empty_count[column] = 0
                    column_count[column] = 0
                if value == None:
                    empty_count[column] += 1
                else:
                    non_null_data[column].append(value)
                column_count[column] += 1
        stats = {}

        for i, col_name in enumerate(non_null_data):
            col_data = non_null_data[col_name] # all rows in just one column
            data_type, data_type_dist = self.getColumnDataType(col_data))
            # NOTE: Enable this if you want to assume that some numeric values can be text
            # We noticed that by default this should not be the behavior
            # TODO: Evaluate if we want to specify the problem type on predict statement as regression or classification
            #
            # if col_name in self.train_meta_data.model_predict_columns and data_type == DATA_TYPES.NUMERIC:
            #     unique_count = len(set(col_data))
            #     if unique_count <= CONFIG.ASSUME_NUMERIC_AS_TEXT_WHEN_UNIQUES_IS_LESS_THAN:
            #         data_type = DATA_TYPES.CLASS

            # Generic stats that can be generated for any data type

            if data_type == DATA_TYPES.DATE:
                for i, element in enumerate(col_data):
                    if str(element) in [str(''), str(None), str(False), str(np.nan), 'NaN', 'nan', 'NA']:
                        col_data[i] = None
                    else:
                        try:
                            col_data[i] = int(parseDate(element).timestamp())
                        except:
                            log.warning('Could not convert string to date and it was expected, current value {value}'.format(value=element))
                            col_data[i] = None

            if data_type == DATA_TYPES.NUMERIC or data_type == DATA_TYPES.DATE:
                newData = []

                for value in col_data:
                    if value != '' and value != '\r' and value != '\n':
                        newData.append(value)


                col_data = [cleanfloat(i) for i in newData if str(i) not in ['', str(None), str(False), str(np.nan), 'NaN', 'nan', 'NA']]

                np_col_data = np.array(col_data).reshape(-1, 1)
                clf = IsolationForest(behaviour='new',contamination='auto', n_estimators=1)
                outliers = clf.fit_predict(np_col_data)

                outlier_indexes = [i for i in range(len(col_data)) if outliers[i] == -1]

                y, x = np.histogram(col_data, 50, density=False)
                x = (x + np.roll(x, -1))[:-1] / 2.0
                x = x.tolist()
                y = y.tolist()

                xp = []

                if len(col_data) > 0:
                    max_value = max(col_data)
                    min_value = min(col_data)
                    mean = np.mean(col_data)
                    median = np.median(col_data)
                    var = np.var(col_data)
                    skew = st.skew(col_data)
                    kurtosis = st.kurtosis(col_data)


                    inc_rate = 0.05
                    initial_step_size = abs(max_value-min_value)/100

                    xp += [min_value]
                    i = min_value + initial_step_size

                    while i < max_value:

                        xp += [i]
                        i_inc = abs(i-min_value)*inc_rate
                        i = i + i_inc


                    # TODO: Solve inc_rate for N
                    #    min*inx_rate + (min+min*inc_rate)*inc_rate + (min+(min+min*inc_rate)*inc_rate)*inc_rate ....
                    #
                    #      x_0 = 0
                    #      x_i = (min+x_(i-1)) * inc_rate = min*inc_rate + x_(i-1)*inc_rate
                    #
                    #      sum of x_i_{i=1}^n (x_i) = max_value = inc_rate ( n * min + sum(x_(i-1)) )
                    #
                    #      mx_value/inc_rate = n*min + inc_rate ( n * min + sum(x_(i-2)) )
                    #
                    #     mx_value = n*min*in_rate + inc_rate^2*n*min + inc_rate^2*sum(x_(i-2))
                    #              = n*min(inc_rate+inc_rate^2) + inc_rate^2*sum(x_(i-2))
                    #              = n*min(inc_rate+inc_rate^2) + inc_rate^2*(inc_rate ( n * min + sum(x_(i-3)) ))
                    #              = n*min(sum_(i=1)^(i=n)(inc_rate^i))
                    #    =>  sum_(i=1)^(i=n)(inc_rate^i)) = max_value/(n*min(sum_(i=1)^(i=n))
                    #
                    # # i + i*x

                else:
                    max_value = 0
                    min_value = 0
                    mean = 0
                    median = 0
                    var = 0
                    skew = 0
                    kurtosis = 0
                    xp = []


                is_float = True if max([1 if int(i) != i else 0 for i in col_data]) == 1 else False


                col_stats = {
                    "column": col_name,
                    KEYS.DATA_TYPE: data_type,
                    # "distribution": best_fit_name,
                    # "distributionParams": distribution_params,
                    "mean": mean,
                    "median": median,
                    "variance": var,
                    "skewness": skew,
                    "kurtosis": kurtosis,
                    "emptyCells": empty_count[col_name],
                    "emptyPercentage": empty_count[col_name] * 100 / column_count[col_name] ,
                    "max": max_value,
                    "min": min_value,
                    "is_float": is_float,
                    "histogram": {
                        "x": x,
                        "y": y
                    },
                    "percentage_buckets": xp,
                    "outlier_indexes": outlier_indexes,
                    "outlier_percentage": len(outlier_indexes) * 100 / column_count[col_name]
                }
                stats[col_name] = col_stats
            # else if its text
            else:
                # see if its a sentence or a word
                is_full_text = True if data_type == DATA_TYPES.FULL_TEXT else False
                dictionary, histogram = self.getWordsDictionary(col_data, is_full_text)

                # if no words, then no dictionary
                if len(col_data) == 0:
                    dictionary_available = False
                    dictionary_lenght_percentage = 0
                    dictionary = []
                else:
                    dictionary_available = True
                    dictionary_lenght_percentage = len(
                        dictionary) / len(col_data) * 100
                    # if the number of uniques is too large then treat is a text
                    if dictionary_lenght_percentage > 10 and len(col_data) > 50 and is_full_text==False:
                        dictionary = []
                        dictionary_available = False
                col_stats = {

                    "column": col_name,
                    KEYS.DATA_TYPE: DATA_TYPES.FULL_TEXT if is_full_text else data_type,
                    "dictionary": dictionary,
                    "dictionaryAvailable": dictionary_available,
                    "dictionaryLenghtPercentage": dictionary_lenght_percentage,
                    "emptyCells": empty_count[col_name],
                    "emptyPercentage": empty_count[col_name] * 100 / column_count[col_name] ,
                    "histogram": histogram
                }
                stats[col_name] = col_stats
            stats[col_name]['data_type_dist'] = data_type_dist


        total_rows = len(self.transaction.input_data.data_array)
        test_rows = len(self.transaction.input_data.test_indexes)
        validation_rows = len(self.transaction.input_data.validation_indexes)
        train_rows = len(self.transaction.input_data.train_indexes)

        self.transaction.persistent_model_metadata.column_stats = stats
        self.transaction.persistent_model_metadata.total_row_count = total_rows
        self.transaction.persistent_model_metadata.test_row_count = test_rows
        self.transaction.persistent_model_metadata.train_row_count = train_rows
        self.transaction.persistent_model_metadata.validation_row_count = validation_rows

        self.transaction.persistent_model_metadata.update()

        for col in stats:
            col_stats = stats[col]

            data_type_tuples = col_stats['data_type_dist'].items()
            significant_data_type_tuples = list(filter(lambda x: x[1] > len(non_null_data[col])/20, data_type_tuples))
            if len(significant_data_type_tuples) > 1:
                log.warning('The data in column "{}" seems to have members of {} different data types, namely {}, We shall go ahead using data type: {}'
                .format(col, len(significant_data_type_tuples), significant_data_type_tuples, col_stats[KEYS.DATA_TYPE]))

            if col_stats['emptyPercentage'] > 10:
                log.warning('The data in column: "{}" has {}% of it\'s values missing'
                .format(col, round(col_stats['emptyPercentage'],2)))

            max_outlier_percentage = 12

            if 'outlier_indexes' in col_stats:
                if col_stats['outlier_percentage'] < max_outlier_percentage:
                    for index in col_stats['outlier_indexes']:
                        log.info('Detect outlier in column "{}", at position "{}", with value "{}"'.
                        format(col,index,non_null_data[col][index]))
                else:
                    log.warning('Detected {}% of the data as outliers in column "{}", this might indicate the data in this column is of low quality'
                    .format( round(col_stats['outlier_percentage'],2) , col ))

        exit()
        return stats



def test():
    from mindsdb import MindsDB
    mdb = MindsDB()

    # We tell mindsDB what we want to learn and from what data
    mdb.learn(
        from_data="https://raw.githubusercontent.com/mindsdb/mindsdb/master/docs/examples/basic/home_rentals.csv",
        # the path to the file where we can learn from, (note: can be url)
        predict='rental_price',  # the column we want to learn to predict given all the data in the file
        model_name='home_rentals',  # the name of this model
        breakpoint=PHASE_STATS_GENERATOR)

# only run the test if this file is called from debugger
if __name__ == "__main__":
    test()
