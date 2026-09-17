"""Offline regressions for real-world connection and backup mistakes."""
import json
from unittest.mock import Mock

import pytest

from app.api_tester import ApiTester
from app.config_manager import ConfigManager
from app.provider_manager import ProviderManager


@pytest.mark.parametrize('suffix', ['', '/', '/v1', '/v1/', '/v1/messages'])
def test_anthropic_endpoint_is_not_duplicated(monkeypatch, suffix):
    response = Mock(status_code=200)
    response.json.return_value = {
        'type': 'message', 'role': 'assistant',
        'content': [{'type': 'text', 'text': 'OK'}],
    }
    post = Mock(return_value=response)
    monkeypatch.setattr('app.api_tester.requests.post', post)
    assert ApiTester.test_provider('https://example.test/anthropic' + suffix,
                                   'test-key', 'test-model')[0]
    assert post.call_args.args[0] == 'https://example.test/anthropic/v1/messages'


@pytest.mark.parametrize('payload', [None, [], {}, {'error': {'message': 'bad'}},
                                     {'status': 'ok'}, {'choices': []}])
def test_http_200_without_anthropic_message_is_not_verified(monkeypatch, payload):
    response = Mock(status_code=200)
    response.json.return_value = payload
    monkeypatch.setattr('app.api_tester.requests.post', Mock(return_value=response))
    ok, message, _ = ApiTester.test_provider('https://example.test', 'secret', 'model')
    assert not ok
    assert '响应' in message
    assert 'secret' not in message


def test_html_login_page_is_not_verified(monkeypatch):
    response = Mock(status_code=200)
    response.json.side_effect = ValueError('HTML login page')
    monkeypatch.setattr('app.api_tester.requests.post', Mock(return_value=response))
    assert not ApiTester.test_provider('https://example.test', 'secret', 'model')[0]


@pytest.mark.parametrize('url', [
    'https://[broken', 'https://example.test:invalid', 'https://example.test:99999',
    'https://user:password@example.test', 'https://example.test?key=secret',
    'https://example.test#fragment', 'https://exam ple.test',
])
def test_bad_url_is_rejected_before_network(monkeypatch, url):
    post = Mock(side_effect=AssertionError('Invalid URL reached the network'))
    monkeypatch.setattr('app.api_tester.requests.post', post)
    assert not ApiTester.test_provider(url, 'secret', 'model')[0]
    assert not ProviderManager._validate_fields('name', url, 'model', 1)[0]
    post.assert_not_called()


def test_default_export_can_be_imported_including_disabled_placeholder(tmp_path):
    manager = ProviderManager(ConfigManager(str(tmp_path / 'data')))
    backup = tmp_path / 'backup.json'
    assert manager.export_config(str(backup))[0]
    ok, message = manager.import_config(str(backup))
    assert ok, message
    assert manager.config.get_provider('DeepSeek')['enabled'] is False


def test_empty_provider_list_can_round_trip(tmp_path):
    manager = ProviderManager(ConfigManager(str(tmp_path / 'data')))
    manager.config.replace_config({'providers': []})
    backup = tmp_path / 'empty.json'
    assert manager.export_config(str(backup))[0]
    assert manager.import_config(str(backup))[0]
    assert manager.config.get_providers() == []


def test_import_string_false_does_not_enable_provider(tmp_path):
    manager = ProviderManager(ConfigManager(str(tmp_path / 'data')))
    original = json.dumps(manager.config.config, sort_keys=True)
    backup = tmp_path / 'invalid.json'
    backup.write_text(json.dumps({'providers': [{
        'name': 'test', 'base_url': 'https://example.test', 'model': 'm',
        'enabled': 'false',
    }]}), encoding='utf-8')
    assert not manager.import_config(str(backup))[0]
    assert json.dumps(manager.config.config, sort_keys=True) == original


@pytest.mark.parametrize('suffix', ['/v1', '/v1/messages'])
def test_saved_provider_and_launcher_use_same_normalized_root(tmp_path, monkeypatch, suffix):
    from app.claude_launcher import ClaudeLauncher
    manager = ProviderManager(ConfigManager(str(tmp_path / 'data')))
    monkeypatch.setattr(manager.cred, 'save_api_key', lambda *args: True)
    root = 'http://127.0.0.1:8787/antigravity'
    ok, message = manager.add_or_update_provider(
        'Local', root + suffix, 'test-model', '', 'fake-key')
    assert ok, message
    assert manager.config.get_provider('Local')['base_url'] == root
    launcher = tmp_path / 'claude.exe'
    launcher.touch()
    monkeypatch.setattr('app.claude_launcher.shutil.which', lambda _: 'cmd.exe')
    popen = Mock()
    monkeypatch.setattr('app.claude_launcher.subprocess.Popen', popen)
    ok, message = ClaudeLauncher.launch(
        'Local', root + suffix, 'fake-key', 'test-model', '',
        str(tmp_path), claude_path=str(launcher))
    assert ok, message
    assert popen.call_args.kwargs['env']['ANTHROPIC_BASE_URL'] == root
