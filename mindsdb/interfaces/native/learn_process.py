import torch.multiprocessing as mp

from mindsdb.interfaces.database.database import DatabaseWrapper
from mindsdb.utilities.os_specific import get_mp_context
from mindsdb.interfaces.storage.db import session, Predictor
from mindsdb.interfaces.storage.fs import FsSotre


ctx = mp.get_context('spawn')

class LearnProcess(ctx.Process):
    daemon = True

    def __init__(self, *args):
        super(LearnProcess, self).__init__(args=args)

    def run(self):
        '''
        running at subprocess due to
        ValueError: signal only works in main thread

        this is work for celery worker here?
        '''
        import mindsdb_native

        fs_store = FsSotre()
        company_id = os.environ.get('MINDSDB_COMPANY_ID', None)

        predictor_record = .query.filter_by(company_id=company_id, name=name)

        id = Column(Integer, primary_key=True)
        updated_at = Column(DateTime, default=datetime.datetime.now, onupdate=datetime.datetime.now)
        created_at = Column(DateTime, default=datetime.datetime.now)
        name = Column(String)
        data = Column(String) # A JSON -- should be everything returned by `get_model_data`, I think
        native_version = Column(String)
        to_predict = Column(String)
        status = Column(String)
        company_id = Column(Integer)
        version = Column(Integer, default=entitiy_version) # mindsdb_native version, can be used in the future for BC
        datasource_id = Column(Integer, ForeignKey('datasource.id'))
        is_custom = Column(Boolean)

        name, from_data, to_predict, kwargs, config = self._args
        mdb = mindsdb_native.Predictor(name=name, run_env={'trigger': 'mindsdb'})

        to_predict = to_predict if isinstance(to_predict, list) else [to_predict]
        data_source = getattr(mindsdb_native, from_data['class'])(*from_data['args'], **from_data['kwargs'])
        mdb.learn(
            from_data=data_source,
            to_predict=to_predict,
            **kwargs
        )

        model_data = mindsdb_native.F.get_model_data(name)

        DatabaseWrapper().register_predictors([model_data])
