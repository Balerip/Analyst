"""

This example we will walk you over the basics of MindsDB

The example code objective here is to:

- learn a model to predict the best retal price for a given property.

In order to to this we have a dataset "data_sources/home_rentals.csv"

"""

from mindsdb import *

# Here we use the model to make predictions (NOTE: You need to run train.py first)
result = MindsDB().predict(predict='Main_Engine_Fuel_Consumption_MT_day', model_name='fuel', from_data = 'fuel.csv')

# you can now print the results
print('The predicted main engine fuel consumption')
print(result)
