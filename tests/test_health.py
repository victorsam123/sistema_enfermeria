from unittest.mock import patch

from sqlalchemy.exc import OperationalError


def test_health_is_public(client):
    response = client.get('/health')
    assert response.status_code == 200
    assert response.json == {'status': 'ok'}


def test_health_database_unavailable(client):
    with patch('app.routes.main.db.session.execute',
               side_effect=OperationalError('SELECT 1', {}, Exception('private-detail'))):
        response = client.get('/health')
    assert response.status_code == 503
    assert response.json == {'status': 'unavailable'}
    assert b'private-detail' not in response.data
