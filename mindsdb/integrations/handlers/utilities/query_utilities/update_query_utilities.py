from mindsdb.integrations.handlers.utilities.query_utilities.base_query_utilities import BaseQueryParser


class UPDATEQueryParser(BaseQueryParser):
    """
    Parses an UPDATE query into its component parts.

    Parameters
    ----------
    query : ast.Update
        Given SQL UPDATE query.
    """
    def __init__(self, query):
        super().__init__(query)
    
    def parse_query(self):
        values_to_update = self.parse_set_clause()
        where_conditions = self.parse_where_clause()

        return values_to_update, where_conditions

    def parse_set_clause(self):
        values = list(self.query.update_columns.items())

        values_to_update = {}
        for value in values:
            values_to_update[value[0]] = value[1].value

        return values_to_update

