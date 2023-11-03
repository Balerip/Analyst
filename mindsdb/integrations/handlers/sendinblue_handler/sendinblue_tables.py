import sib_api_v3_sdk
import pandas as pd

from typing import List, Optional, Dict, Text
from mindsdb.utilities.log import get_log
from mindsdb.integrations.libs.api_handler import APITable
logger = get_log("integrations.sendinblue_handler")
from mindsdb_sql.parser import ast
from sib_api_v3_sdk.rest import ApiException
from datetime import datetime

from mindsdb.integrations.handlers.utilities.query_utilities import SELECTQueryParser, SELECTQueryExecutor, UPDATEQueryExecutor, UPDATEQueryParser, DELETEQueryParser, DELETEQueryExecutor


class EmailCampaignsTable(APITable):
    """The Sendinblue Email Campaigns Table implementation"""

    def select(self, query: ast.Select) -> pd.DataFrame:
        """Pulls data from the Sendinblue "GET /emailCampaigns" API endpoint.

        Parameters
        ----------
        query : ast.Select
           Given SQL SELECT query

        Returns
        -------
        pd.DataFrame
            Sendinblue Email Campaigns matching the query

        Raises
        ------
        ValueError
            If the query contains an unsupported condition
        """
 
        select_statement_parser = SELECTQueryParser(
            query,
            'email_campaigns',
            self.get_columns()
        )
        selected_columns, where_conditions, order_by_conditions, result_limit = select_statement_parser.parse_query()

        email_campaigns_df = pd.json_normalize(self.get_email_campaigns(limit=result_limit))

        select_statement_executor = SELECTQueryExecutor(
            email_campaigns_df,
            selected_columns,
            where_conditions,
            order_by_conditions
        )
        email_campaigns_df = select_statement_executor.execute_query()

        return email_campaigns_df

    def get_columns(self) -> List[str]:
        return pd.json_normalize(self.get_email_campaigns(limit=1)).columns.tolist()

    def get_email_campaigns(self, **kwargs):
        connection = self.handler.connect()
        email_campaigns_api_instance = sib_api_v3_sdk.EmailCampaignsApi(connection)
        email_campaigns = email_campaigns_api_instance.get_email_campaigns(**kwargs)
        return [email_campaign for  email_campaign in email_campaigns.campaigns]
              
    def delete(self, query: ast.Delete) -> None:
        """
        Deletes an email campaign from Sendinblue.

        Parameters
        ----------
        query : ast.Delete
           Given SQL DELETE query

        Returns
        -------
        None

        Raises
        ------
        ApiException
            If an error occurs when calling Sendinblue's API
        """
        # this  parses the DELETE statement to extract where conditions
        delete_statement_parser = DELETEQueryParser(query)
        where_conditions = delete_statement_parser.parse_query()
        # this retrieves the current list of email campaigns and normalize the data into a DataFrame
        email_campaigns_df = pd.json_normalize(self.get_email_campaigns())
        # this execute the delete query  to filter out the campaigns to be deleted
        delete_query_executor = DELETEQueryExecutor(
            email_campaigns_df,
            where_conditions
        )
        # this gets the updated DataFrame after executing  delete conditions
        email_campaigns_df = delete_query_executor.execute_query()
        campaign_ids = email_campaigns_df['id'].tolist()
        self.delete_email_campaigns(campaign_ids)

    def delete_email_campaigns(self, campaign_ids: List[Text]) -> None:
        #this establish a connection to Sendinblue API
        connection = self.handler.connect()
        email_campaigns_api_instance = sib_api_v3_sdk.EmailCampaignsApi(connection)

        for campaign_id in campaign_ids:
            try:
                email_campaigns_api_instance.delete_email_campaign(campaign_id)
                logger.info(f'Email Campaign {campaign_id} deleted')
            except ApiException as e:
                logger.error(f"Exception when calling EmailCampaignsApi->delete_email_campaign: {e}\n")           
