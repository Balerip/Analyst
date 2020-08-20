import datetime
import os
import threading
import tempfile

import multipart

import mindsdb
from dateutil.parser import parse
from flask import request, send_file
from flask_restx import Resource, abort
from flask import current_app as ca

from mindsdb.interfaces.datastore.sqlite_helpers import *
from mindsdb.api.http.namespaces.configs.datasources import ns_conf
from mindsdb.api.http.namespaces.entitites.datasources.datasource import (
    datasource_metadata,
    put_datasource_params
)
from mindsdb.api.http.namespaces.entitites.datasources.datasource_data import (
    get_datasource_rows_params,
    datasource_rows_metadata
)
from mindsdb.api.http.namespaces.entitites.datasources.datasource_files import (
    put_datasource_file_params
)
from mindsdb.api.http.namespaces.entitites.datasources.datasource_missed_files import (
    datasource_missed_files_metadata,
    get_datasource_missed_files_params
)


@ns_conf.route('/')
class DatasourcesList(Resource):
    @ns_conf.doc('get_datasources_list')
    @ns_conf.marshal_list_with(datasource_metadata)
    def get(self):
        '''List all datasources'''
        return ca.default_store.get_datasources()


@ns_conf.route('/<name>')
@ns_conf.param('name', 'Datasource name')
class Datasource(Resource):
    @ns_conf.doc('get_datasource')
    @ns_conf.marshal_with(datasource_metadata)
    def get(self, name):
        '''return datasource metadata'''
        ds = ca.default_store.get_datasource(name)
        if ds is not None:
            return ds
        return '', 404

    @ns_conf.doc('delete_datasource')
    def delete(self, name):
        '''delete datasource'''
        try:
            ca.default_store.delete_datasource(name)
        except Exception as e:
            print(e)
            abort(400, str(e))
        return '', 200

    @ns_conf.doc('put_datasource', params=put_datasource_params)
    @ns_conf.marshal_with(datasource_metadata)
    def put(self, name):
        '''add new datasource'''
        data = {}

        def on_field(field):
            print(f'\n\n{field}\n\n')
            name = field.field_name.decode()
            value = field.value.decode()
            data[name] = value

        def on_file(file):
            data['file'] = file.file_name.decode()
            f = file.file_object
            if not f.closed:
                f.close()

        temp_dir_path = tempfile.mkdtemp(prefix='datasource_file_')

        if request.headers['Content-Type'].startswith('multipart/form-data'):
            parser = multipart.create_form_parser(
                headers=request.headers,
                on_field=on_field,
                on_file=on_file,
                config={
                    'UPLOAD_DIR': temp_dir_path.encode(),    # bytes required
                    'UPLOAD_KEEP_FILENAME': True,
                    'UPLOAD_KEEP_EXTENSIONS': True,
                    'MAX_MEMORY_FILE_SIZE': 0
                }
            )

            while True:
                chunk = request.stream.read(8192)
                if not chunk:
                    break
                parser.write(chunk)
            parser.finalize()
            parser.close()
        else:
            data = request.json

        if 'query' in data:
            query = request.json['query']
            source_type = request.json['integration_id']
            ca.default_store.save_datasource(name, source_type, query)
            os.rmdir(temp_dir_path)
            return ca.default_store.get_datasource(name)

        ds_name = data['name'] if 'name' in data else name
        source = data['source'] if 'source' in data else name
        source_type = data['source_type']

        if source_type == 'file':
            file_path = os.path.join(temp_dir_path, data['file'])
        else:
            file_path = None

        ca.default_store.save_datasource(ds_name, source_type, source, file_path)
        os.rmdir(temp_dir_path)

        return ca.default_store.get_datasource(ds_name)


ds_analysis = {}


def analyzing_thread(name, default_store):
    global ds_analysis
    ds_analysis[name] = None
    ds = default_store.get_datasource(name)
    analysis = default_store.get_analysis(ds['name'])
    ds_analysis[name] = {
        'created_at': datetime.datetime.utcnow(),
        'data': analysis
    }


@ns_conf.route('/<name>/analyze')
@ns_conf.param('name', 'Datasource name')
class Analyze(Resource):
    @ns_conf.doc('analyse_dataset')
    def get(self, name):
        global ds_analysis
        if name in ds_analysis:
            if ds_analysis[name] is None:
                return {'status': 'analyzing'}, 200
            elif (datetime.datetime.utcnow() - ds_analysis[name]['created_at']) > datetime.timedelta(seconds=10):
                del ds_analysis[name]
            else:
                analysis = ds_analysis[name]['data']
                return analysis, 200

        ds = ca.default_store.get_datasource(name)
        if ds is None:
            print('No valid datasource given')
            abort(400, 'No valid datasource given')

        if ds['row_count'] <= 10000:
            analysis = ca.default_store.get_analysis(ds['name'])
            return analysis, 200
        else:
            x = threading.Thread(target=analyzing_thread, args=(name, ca.default_store))
            x.start()
            return {'status': 'analyzing'}, 200


@ns_conf.route('/<name>/analyze_subset')
@ns_conf.param('name', 'Datasource name')
class AnalyzeSubset(Resource):
    @ns_conf.doc('analyse_datasubset')
    def get(self, name):
        ds = ca.default_store.get_datasource(name)
        if ds is None:
            print('No valid datasource given')
            abort(400, 'No valid datasource given')

        where = []
        for key, value in request.args.items():
            if key.startswith('filter'):
                param = parse_filter(key, value)
                if param is None:
                    abort(400, f'Not valid filter "{key}"')
                where.append(param)

        data_dict = ca.default_store.get_data(ds['name'], where)

        if data_dict['rowcount'] == 0:
            return abort(400, 'Empty dataset after filters applying')

        return get_analysis(pd.DataFrame(data_dict['data'])), 200


@ns_conf.route('/<name>/data/')
@ns_conf.param('name', 'Datasource name')
class DatasourceData(Resource):
    @ns_conf.doc('get_datasource_data', params=get_datasource_rows_params)
    @ns_conf.marshal_with(datasource_rows_metadata)
    def get(self, name):
        '''return data rows'''
        ds = ca.default_store.get_datasource(name)
        if ds is None:
            abort(400, 'No valid datasource given')

        params = {
            'page[size]': None,
            'page[offset]': None
        }
        where = []
        for key, value in request.args.items():
            if key == 'page[size]':
                params['page[size]'] = int(value)
            if key == 'page[offset]':
                params['page[offset]'] = int(value)
            elif key.startswith('filter'):
                param = parse_filter(key, value)
                if param is None:
                    abort(400, f'Not valid filter "{key}"')
                where.append(param)

        data_dict = ca.default_store.get_data(name, where, params['page[size]'], params['page[offset]'])

        return data_dict, 200


@ns_conf.route('/<name>/download')
@ns_conf.param('name', 'Datasource name')
class DatasourceMissedFilesDownload(Resource):
    @ns_conf.doc('get_datasource_download')
    def get(self, name):
        '''download uploaded file'''
        ds = ca.default_store.get_datasource(name)
        if not ds:
            abort(404, "{} not found".format(name))
        if not os.path.exists(ds['source']):
            abort(404, "{} not found".format(name))

        return send_file(os.path.abspath(ds['source']), as_attachment=True)
