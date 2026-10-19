import base64
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
from proposal.model_config_security import encrypt_config, decrypt_config
from proposal.supabase_store import SupabaseStore, request_identity


def test_aead_config_is_random_authenticated_and_bound_to_account(monkeypatch):
    monkeypatch.setenv('USER_CONFIG_ENCRYPTION_KEY', base64.urlsafe_b64encode(b'x' * 32).decode())
    config = {'api_key': 'hidden-provider-key', 'image_api_key': 'hidden-image-key'}
    a = encrypt_config('A', config)
    b = encrypt_config('A', config)
    assert a != b
    assert 'hidden' not in a
    assert decrypt_config('A', a) == config
    with pytest.raises(RuntimeError):
        decrypt_config('B', a)
    with pytest.raises(RuntimeError):
        decrypt_config('A', a[:-8] + 'a' * 8)
    monkeypatch.delenv('USER_CONFIG_ENCRYPTION_KEY')
    with pytest.raises(RuntimeError):
        encrypt_config('A', config)


def test_cloud_persistence_contains_only_ciphertext_and_current_owner(monkeypatch, tmp_path):
    monkeypatch.setenv('USER_CONFIG_ENCRYPTION_KEY', base64.urlsafe_b64encode(b'y' * 32).decode())
    import proposal.supabase_store as module
    captured = []
    def upstream(request, timeout):
        captured.append(request)
        return io.BytesIO(b'')
    monkeypatch.setattr(module, 'supabase_urlopen', upstream)
    store = SupabaseStore('https://fixed.supabase.co', 'publishable', tmp_path)
    token = request_identity.set({'user_id': 'owner-A', 'access_token': 'jwt-A'})
    try:
        store.save_model_config({'api_key': 'secret-provider-key'})
    finally:
        request_identity.reset(token)
    payload = json.loads(captured[0].data)
    assert payload['owner_id'] == 'owner-A'
    assert 'secret-provider-key' not in captured[0].data.decode()
    assert captured[0].get_header('Authorization') == 'Bearer jwt-A'
    assert decrypt_config('owner-A', payload['ciphertext'])['api_key'] == 'secret-provider-key'
    with pytest.raises(PermissionError):
        store.get_model_config()


@pytest.mark.skipif(os.environ.get('RUN_POSTGRES_POLICY_TESTS') != '1', reason='Opt-in isolated Postgres RLS test')
def test_real_rls_config_isolation():
    name = 'model-config-qa-' + uuid.uuid4().hex[:8]
    subprocess.run(['docker', 'run', '--rm', '--pull=never', '--network=none', '-d', '--name', name,
                    '-e', 'POSTGRES_HOST_AUTH_METHOD=trust', 'postgres:15-alpine'], check=True, capture_output=True)
    def sql(source, ok=True):
        result = subprocess.run(['docker', 'exec', '-i', name, 'psql', '-U', 'postgres', '-v', 'ON_ERROR_STOP=1', '-Atq'],
            input=source, text=True, capture_output=True, timeout=30)
        assert (result.returncode == 0) == ok, result.stderr
        return result.stdout.strip()
    a = '00000000-0000-4000-8000-000000000001'
    b = '00000000-0000-4000-8000-000000000002'
    try:
        for _ in range(50):
            if subprocess.run(['docker', 'exec', name, 'pg_isready', '-h', '127.0.0.1'], capture_output=True).returncode == 0: break
            time.sleep(.1)
        sql('''create role anon; create role authenticated; create schema auth;
            create table auth.users (id uuid primary key);
            create function auth.uid() returns uuid language sql stable as $$
              select nullif(current_setting('request.jwt.claim.sub', true), '')::uuid $$;
            grant usage on schema auth to authenticated;''')
        migration = Path(__file__).resolve().parents[1] / 'supabase/migrations/20261019172715_encrypted_user_model_config.sql'
        sql(migration.read_text())
        sql(f"insert into auth.users values ('{a}'), ('{b}');")
        prefix = f"set role authenticated; set request.jwt.claim.sub='{a}';"
        sql(prefix + f"insert into public.user_model_configs(owner_id,ciphertext) values ('{a}',repeat('a',50));")
        assert sql(f"set role authenticated; set request.jwt.claim.sub='{b}'; select count(*) from public.user_model_configs;") == '0'
        sql(prefix + f"update public.user_model_configs set owner_id='{b}' where owner_id='{a}';", ok=False)
        sql(f"set role anon; select * from public.user_model_configs;", ok=False)
        sql(f"set role authenticated; set request.jwt.claim.sub='{b}'; delete from public.user_model_configs;")
        assert sql(prefix + 'select count(*) from public.user_model_configs;') == '1'
        sql(prefix + 'delete from public.user_model_configs;')
        assert sql(prefix + 'select count(*) from public.user_model_configs;') == '0'
    finally:
        subprocess.run(['docker', 'rm', '-f', name], capture_output=True)


def test_pooled_transport_uses_per_request_auth_not_previous_account(monkeypatch):
    import httpx
    import urllib.request
    import proposal.supabase_http as transport
    seen = []
    def handle(request):
        seen.append(dict(request.headers))
        return httpx.Response(200, json=[], headers={'set-cookie': 'unexpected-session=old; Path=/'})
    with httpx.Client(transport=httpx.MockTransport(handle)) as client:
        monkeypatch.setattr(transport, '_client', client)
        for owner in ('A', 'B'):
            request = urllib.request.Request('https://fixed.supabase.co/rest/v1/projects',
                headers={'Authorization': f'Bearer jwt-{owner}', 'apikey': 'public'})
            with transport.supabase_urlopen(request) as response:
                assert response.read() == b'[]'
    assert seen[0]['authorization'] == 'Bearer jwt-A'
    assert seen[1]['authorization'] == 'Bearer jwt-B'
    assert seen[1].get('cookie', '') == ''
