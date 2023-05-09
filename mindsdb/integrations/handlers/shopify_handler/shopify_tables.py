import shopify
import pandas as pd

from typing import List

from mindsdb.integrations.libs.api_handler import APITable
from mindsdb.integrations.utilities.sql_utils import extract_comparison_conditions

from mindsdb_sql.parser import ast

from mindsdb.utilities import log


def filter_df(df, conditions):
    for condition in conditions:
        column = condition[1]
        operator = '==' if condition[0] == '=' else condition[0]
        value = f"'{condition[2]}'" if type(condition[2]) == str else condition[2]

        query = f"{column} {operator} {value}"
        df.query(query, inplace=True)

    return df


class ProductsTable(APITable):
    """The Shopify Products Table implementation"""

    def select(self, query: ast.Select) -> pd.DataFrame:
        """Pulls data from the Shopify "GET /products" API endpoint.

        Parameters
        ----------
        query : ast.Select
           Given SQL SELECT query

        Returns
        -------
        pd.DataFrame
            Shopify Products matching the query

        Raises
        ------
        ValueError
            If the query contains an unsupported condition
        """
        pass