from app.gcli2api_manager import Gcli2ApiManager


def test_new_and_legacy_transport_aliases_collapse():
    models = Gcli2ApiManager.clean_claude_models([
        'gemini-3.8-flash', '抗截断/gemini-3.8-flash',
        '假流式/抗截断/gemini-3.8-flash', '流式抗截断/gemini-3.8-flash',
    ])
    assert models == ('gemini-3.8-flash',)


def test_newer_flash_generation_first_without_inventing_models():
    models = Gcli2ApiManager.clean_claude_models([
        'gemini-2.5-flash', 'gemini-3.8-flash', 'gemini-3.10-flash',
        'gemini-3.8-flash-image', 'claude-sonnet-4-6',
    ])
    assert models == ('claude-sonnet-4-6', 'gemini-3.10-flash',
                      'gemini-3.8-flash', 'gemini-2.5-flash')
    assert Gcli2ApiManager.clean_claude_models(['gemini-2.5-flash']) == ('gemini-2.5-flash',)
