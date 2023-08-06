import overpy
import pandas as pd
from typing import Text, List, Dict

from mindsdb_sql.parser import ast
from mindsdb.integrations.libs.api_handler import APITable

from mindsdb.integrations.handlers.utilities.query_utilities import SELECTQueryParser, SELECTQueryExecutor


class OpenStreetMapNodeTable(APITable):
    """The OpenStreetMap Nodes Table implementation"""

    def select(self, query: ast.Select) -> pd.DataFrame:
        """Pulls data from the OpenStreetMap API endpoint.

        Parameters
        ----------
        query : ast.Select
           Given SQL SELECT query

        Returns
        -------
        pd.DataFrame
            OpenStreetMap data matching the query

        Raises
        ------
        ValueError
            If the query contains an unsupported condition
        """

        select_statement_parser = SELECTQueryParser(
            query,
            'nodes',
            self.get_columns()
        )
        selected_columns, where_conditions, order_by_conditions, result_limit = select_statement_parser.parse_query()

        nodes_df = pd.json_normalize(self.get_nodes(limit=result_limit))

        select_statement_executor = SELECTQueryExecutor(
            nodes_df,
            selected_columns,
            where_conditions,
            order_by_conditions
        )
        nodes_df = select_statement_executor.execute_query()

        return nodes_df
    
    def get_columns(self) -> List[Text]:
        return pd.json_normalize(self.get_nodes()).columns.tolist()
    
    def get_nodes(self, **kwargs) -> List[Dict]:
            
        api_session = self.handler.connect()
        nodes = api_session.query("""
            node
            ({{bbox}});
            out;
            """,
        )
        return [node.to_dict() for node in nodes.nodes]

    def execute_osm_node_query(self, tag_key, tag_value, area=None, min_lat=None, min_lon=None, max_lat=None, max_lon=None):
        query_template = """
        [out:json];
        {area_clause}
        node{area_node_clause}["{tag_key}"="{tag_value}"]{bbox};
        out;
        """

        area_clause, area_node_clause = "", ""
        if area:
            area_clause = 'area[name="{}"]->.city;\n'.format(area)
            area_node_clause = "(area.city)"

        bbox_clause = ""
        if min_lat or min_lon or max_lat or max_lon:
            bbox_clause = "{},{},{},{}".format(min_lat, min_lon, max_lat, max_lon)

        query = query_template.format(
            area_clause=area_clause,
            area_node_clause=area_node_clause,
            tag_key=tag_key,
            tag_value=tag_value,
            bbox=bbox_clause
        )

        api = self.handler.connect()

        result = api.query(query)
        return result
    

class OpenStreetMapWayTable(APITable):
    """The OpenStreetMap Ways Table implementation"""

    def select(self, query: ast.Select) -> pd.DataFrame:

        select_statement_parser = SELECTQueryParser(
            query,
            'ways',
            self.get_columns()
        )
        selected_columns, where_conditions, order_by_conditions, result_limit = select_statement_parser.parse_query()

        ways_df = pd.json_normalize(self.get_ways(limit=result_limit))

        select_statement_executor = SELECTQueryExecutor(
            ways_df,
            selected_columns,
            where_conditions,
            order_by_conditions
        )
        ways_df = select_statement_executor.execute_query()

        return ways_df
    
    def get_columns(self) -> List[Text]:
        return pd.json_normalize(self.get_ways(limit=1)).columns.tolist()
    
    def get_ways(self, **kwargs) -> List[Dict]:

        api_session = self.handler.connect()
        ways = api_session.query("""
            way
            ({{bbox}});
            out;
            """,
           # bbox=self.connection_data['bbox']
        )
        return [way.to_dict() for way in ways.ways]
    
    
    
class OpenStreetMapRelationTable(APITable):
    """The OpenStreetMap Relations Table implementation"""

    def select_relations(self, query: ast.Select) -> pd.DataFrame:

        select_statement_parser = SELECTQueryParser(
            query,
            'relations',
            self.get_columns()
        )
        selected_columns, where_conditions, order_by_conditions, result_limit = select_statement_parser.parse_query()

        relations_df = pd.json_normalize(self.get_relations(limit=result_limit))
        
        select_statement_executor = SELECTQueryExecutor(
            relations_df,
            selected_columns,
            where_conditions,
            order_by_conditions
        )
        relations_df = select_statement_executor.execute_query()

        return relations_df
    
    def get_columns(self) -> List[Text]:
        return pd.json_normalize(self.get_relations(limit=1)).columns.tolist()
    
    def get_relations(self, **kwargs) -> List[Dict]:
                
                api_session = self.handler.connect()
                relations = api_session.query("""
                    relation
                    ({{bbox}});
                    out;
                    """,
                   # bbox=self.connection_data['bbox']
                )
                return [relation.to_dict() for relation in relations.relations]
    
