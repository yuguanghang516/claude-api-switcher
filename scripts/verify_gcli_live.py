"""Local verification; never prints passwords or upstream credential contents."""
import json
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import requests
from app.credential_manager import CredentialManager
from app.gcli2api_manager import Gcli2ApiManager

data = Path.home() / 'AppData/Local/ClaudeAPISwitcher/data'
config = json.loads((data / 'config.json').read_text(encoding='utf-8'))
provider = next(p for p in config['providers'] if p.get('provider_kind') == 'gcli2api')
password = CredentialManager.get_api_key(provider.get('id') or provider['name'])
if not password:
    raise SystemExit('No saved local API password')
manager = Gcli2ApiManager(data, request_timeout=30)
try:
    ok, message, status = manager.start_and_wait(password, timeout=60)
    print(json.dumps({'started': ok, 'state': status.state, 'version': status.version}, ensure_ascii=False), flush=True)
    models = manager.clean_claude_models(status.models)
    candidates = [m for m in models if m.startswith('gemini-3.8-flash')]
    print(json.dumps({'gemini_38_models': candidates, 'text_models': list(models)}, ensure_ascii=False), flush=True)
    if candidates:
        model = 'gemini-3.8-flash' if 'gemini-3.8-flash' in candidates else candidates[0]
        response = requests.post(manager.gateway_base_url('antigravity') + '/chat/completions',
            headers={'Authorization': 'Bearer ' + password},
            json={'model': model, 'messages': [{'role': 'user', 'content': 'Reply with OK only.'}],
                  'max_tokens': 256, 'stream': False}, timeout=90)
        result = {'tested_model': model, 'http_status': response.status_code}
        if response.ok:
            payload = response.json()
            result['response_model'] = payload.get('model')
            result['has_content'] = bool(payload.get('choices', [{}])[0].get('message', {}).get('content'))
        else:
            result['error'] = manager._safe_response_detail(response)
        print(json.dumps(result, ensure_ascii=False), flush=True)
finally:
    manager.stop_managed()
