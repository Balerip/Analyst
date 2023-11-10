import copy
from typing import List

import pandas as pd

import mindsdb_sql.planner.utils as utils
from mindsdb_sql.parser.ast import (
    BinaryOperation,
    Constant,
    Identifier,
    Select,
    Update,
    Delete,
    Star
)

import mindsdb.interfaces.storage.db as db
from mindsdb.integrations.libs.vectordatabase_handler import TableField


class KnowledgeBaseTable:
    def __init__(self, kb: db.KnowledgeBase, session):
        self._kb = kb
        self._vector_db = None
        self.session = session

    def select_query(self, query: Select):
        # replace content with embeddings

        utils.query_traversal(query.where, self._replace_query_content)

        # set table name
        query.from_table = Identifier(parts=[self._kb.vector_database_table])

        # remove embeddings from result
        targets = []
        for target in query.targets:
            if isinstance(target, Star):
                targets.extend([
                    Identifier(TableField.ID.value),
                    Identifier(TableField.CONTENT.value),
                    Identifier(TableField.METADATA.value),
                ])
            elif isinstance(target, Identifier) and target.parts[-1].lower() != TableField.EMBEDDINGS.value:
                targets.append(target)
        query.targets = targets

        # send to vectordb
        db_handler = self._get_vector_db()
        resp = db_handler.query(query)
        return resp.data_frame

    def update_query(self, query: Update):
        # add embeddings to content in updated collumns
        query = copy.deepcopy(query)

        emb_col = TableField.EMBEDDINGS.value
        cont_col = TableField.CONTENT.value
        if cont_col in query.update_columns:
            content = query.update_columns[cont_col]
            query.update_columns[emb_col] = Constant(self._content_to_embeddings(content))

        # TODO search content in where clause?

        # set table name
        query.table = Identifier(parts=[self._kb.vector_database_table])

        # send to vectordb
        db_handler = self._get_vector_db()
        return db_handler.query(query)

    def delete_query(self, query: Delete):
        utils.query_traversal(query.where, self._replace_query_content)

        # set table name
        query.table = Identifier(parts=[self._kb.vector_database_table])

        # send to vectordb
        db_handler = self._get_vector_db()
        db_handler.query(query)

    def insert(self, df: pd.DataFrame):
        if df.empty:
            return

        # add embeddings
        df_emb = self._df_to_embeddings(df)
        df = pd.concat([df, df_emb], axis=1)

        # send to vector db
        db_handler = self._get_vector_db()
        db_handler.do_upsert(self._kb.vector_database_table, df)

    def _replace_query_content(self, node, **kwargs):
        if isinstance(node, BinaryOperation):
            if isinstance(node.args[0], Identifier) and isinstance(node.args[1], Constant):
                col_name = node.args[0].parts[-1]
                if col_name.lower() == TableField.CONTENT.value:
                    # replace
                    node.args[0].parts = [TableField.EMBEDDINGS.value]
                    node.args[1].value = [self._content_to_embeddings(node.args[1].value)]

    def _get_vector_db(self):
        if self._vector_db is None:
            database_name = db.Integration.query.get(self._kb.vector_database_id).name
            self._vector_db = self.session.integration_controller.get_handler(database_name)
        return self._vector_db

    def _df_to_embeddings(self, df):
        model_id = self._kb.embedding_model_id
        # get the input columns
        model_rec = db.session.query(db.Predictor).filter_by(id=model_id).first()

        assert model_rec is not None, f"Model not found: {model_id}"
        model_project = db.session.query(db.Project).filter_by(id=model_rec.project_id).first()

        project_datanode = self.session.datahub.get(model_project.name)

        # TODO adjust input
        input_col = model_rec.learn_args.get('using', {}).get('question_column')
        if input_col is not None and input_col != TableField.CONTENT.value:
            df = df.rename(columns={TableField.CONTENT.value: input_col})

        if df.empty:
            df_out = pd.DataFrame([], columns=[TableField.EMBEDDINGS.value])
        else:
            data = df.to_dict('records')

            df_out = project_datanode.predict(
                model_name=model_rec.name,
                data=data,
            )

            target = model_rec.to_predict[0]
            if target != TableField.EMBEDDINGS.value:
                # adapt output for vectordb
                df_out = df_out.rename(columns={target: TableField.EMBEDDINGS.value})

        return df_out

    def _content_to_embeddings(self, content):

        df = pd.DataFrame([[content]], columns=[TableField.CONTENT.value])
        res = self._df_to_embeddings(df)
        return res[TableField.EMBEDDINGS.value][0]


class KnowledgeBaseController:
    """
    Knowledge bae controller handles all
    db related operations for knowledge bases
    """

    def __init__(self, session) -> None:
        self.session = session

    def add(
        self,
        name: str,
        project_name: str,
        embedding_model: Identifier,
        storage: Identifier,
        params: dict,
        if_not_exists: bool = False,
    ):
        """
        Add a new knowledge base to the database
        """
        # check if knowledge base already exists

        # get project id

        project = self.session.database_controller.get_project(project_name)

        project_id = project.id

        # not difference between cases in sql
        name = name.lower()

        kb = self.get(name, project_id)
        if kb is not None:
            if if_not_exists:
                return kb
            else:
                raise Exception(f"Knowledge base already exists: {name}")

        # model
        model_name = embedding_model.parts[-1]

        if len(embedding_model.parts) > 1:
            # model project is set
            model_project = self.session.database_controller.get_project(embedding_model.parts[-2])
        else:
            model_project = project

        model = self.session.model_controller.get_model(
            model_name,
            project_name=model_project.name
        )
        model_record = db.Predictor.query.get(model['id'])
        embedding_model_id = model_record.id

        # search for the vector database table
        if storage is None:
            # create chroma db with same name
            vector_table_name = "default_collection"
            vector_db_name = self._create_persistent_chroma(
                name
            )
        elif len(storage.parts) != 2:
            raise Exception('Storage param has to be vector db with table')
        else:
            vector_db_name, vector_table_name = storage.parts

        vector_database_id = self.session.integration_controller.get(vector_db_name)['id']

        # create table in vectordb
        self.session.datahub.get(vector_db_name).integration_handler.create_table(
            vector_table_name
        )

        kb = db.KnowledgeBase(
            name=name,
            project_id=project_id,
            vector_database_id=vector_database_id,
            vector_database_table=vector_table_name,
            embedding_model_id=embedding_model_id,
            params=params,
        )
        db.session.add(kb)
        db.session.commit()
        return kb

    def _create_persistent_chroma(self, kb_name, engine="chromadb"):
        """Create default vector database for knowledge base, if not specified"""

        vector_store_name = f"{kb_name}_{engine}"

        vector_store_folder_name = f"{vector_store_name}"
        connection_args = {"persist_directory": vector_store_folder_name}

        # check if exists
        if self.session.integration_controller.get(vector_store_name):
            return vector_store_name

        self.session.integration_controller.add(vector_store_name, engine, connection_args)
        return vector_store_name

    def delete(self, name: str, project_name: str, if_exists: bool = False) -> None:
        """
        Delete a knowledge base from the database
        """
        try:
            project = self.session.database_controller.get_project(project_name)
        except ValueError:
            raise Exception(f"Project not found: {project_name}")
        project_id = project.id

        # check if knowledge base exists
        kb = self.get(name, project_id)
        if kb is None:
            # knowledge base does not exist
            if if_exists:
                return
            else:
                raise Exception(f"Knowledge base does not exist: {name}")

        # drop table
        database_name = db.Integration.query.get(kb.vector_database_id).name
        self.session.datahub.get(database_name).integration_handler.drop_table(
            kb.vector_database_table
        )

        # kb exists
        db.session.delete(kb)
        db.session.commit()

    def get(self, name: str, project_id: str):
        """
        Get a knowledge base from the database
        by name + project_id
        """
        kb = (
            db.session.query(db.KnowledgeBase)
            .filter_by(
                name=name,
                project_id=project_id,
            )
            .first()
        )
        return kb

    def get_table(self, name: str, project_id: str):
        kb = self.get(name, project_id)
        if kb is not None:
            return KnowledgeBaseTable(kb, self.session)

    def list(self, project_id: str) -> List[db.KnowledgeBase]:
        """
        List all knowledge bases from the database
        belonging to a project
        """
        kbs = (
            db.session.query(db.KnowledgeBase)
            .filter_by(
                project_id=project_id,
            )
            .all()
        )
        return kbs

    def update(self, name: str, project_id: str, **kwargs) -> db.KnowledgeBase:
        """
        Update a knowledge base from the database
        """
        raise NotImplementedError()
