import threading
import httpx
import pytest
from scripts.preview import PreviewServer


@pytest.fixture
def preview():
    server = PreviewServer(0)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    url = f"http://127.0.0.1:{server.server_port}"
    with httpx.Client(base_url=url, headers={"Origin": url, "X-CSRF-Token": "sample-preview-only"}) as client:
        yield client
    server.shutdown()
    server.server_close()
    thread.join()


def test_preview_is_labeled_and_has_synthetic_data(preview):
    data = preview.get('/api/snapshot').json()
    assert data['preview'] is True
    assert len(data['jobs']) == 6
    assert data['settings']['paused'] is True
    assert data['account'] is None


def test_preview_controls_only_change_memory(preview):
    assert preview.post('/api/queue/resume').json()['paused'] is False
    assert preview.post('/api/jobs/sample-4/retry').status_code == 200
    assert preview.get('/api/snapshot').json()['jobs'][4]['state'] == 'QUEUED'


def test_preview_blocks_real_operations_and_cross_origin(preview):
    assert preview.post('/api/account/connect').status_code == 409
    assert preview.post('/api/imports', json={'filename':'personal.mov'}).status_code == 409
    assert preview.post('/api/watches', json={'path':'C:\\'}).status_code == 409
    assert preview.post('/api/queue/resume', headers={'Origin':'https://evil.example'}).status_code == 403
