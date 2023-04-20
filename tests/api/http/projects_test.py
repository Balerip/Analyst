import os
import pytest
from tempfile import TemporaryDirectory

from mindsdb.api.http.initialize import initialize_app
from mindsdb.migrations import migrate
from mindsdb.interfaces.storage import db
from mindsdb.utilities.config import Config


@pytest.fixture(scope="session", autouse=True)
def app():
    with TemporaryDirectory(prefix='projects_test_') as temp_dir:
        db_path = 'sqlite:///' + os.path.join(temp_dir, 'mindsdb.sqlite3.db')
        db.init(db_path)
        migrate.migrate_to_head()
        app = initialize_app(Config(), True, False)

        yield app


@pytest.fixture()
def client(app):
    return app.test_client()


def test_get_projects(client):
    response = client.get('/api/projects', follow_redirects=True)
    all_projects = response.get_json()
    # Should contain default project.
    assert len(all_projects) == 1
    assert all_projects[0]['name'] == 'mindsdb'


def test_get_project(client):
    response = client.get('/api/projects/mindsdb', follow_redirects=True)
    default_project = response.get_json()
    assert default_project['name'] == 'mindsdb'


def test_get_project_not_found(client):
    response = client.get('/api/projects/zoop', follow_redirects=True)
    assert '404' in response.status
