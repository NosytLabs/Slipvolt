"""The setup command must diagnose, never initialize or disclose secrets."""
import json
import os
from pathlib import Path+import subprocess
import sys
import pytest

ROOT=Path(__file__).resolve().parents[1]

def run_doctor(tmp_path, lines):
    target=tmp_path/'private.env';target.write_text(lines);target.chmod(0o600)
    env={k:v for k,v in os.environ.items() if not k.startswith(('APP_','KEY_','ADMIN_','OPENBROKER_','HOLDER_','MIN_HOLDING_','SOLANA_','DATABASE_','ACCESS_'))}
    env['PYTHONPATH']=str(ROOT)
    result=subprocess.run([sys.executable,'-m','gridraft.cli','--env-file',str(target),'doctor'],cwd=tmp_path,env=env,text=True,capture_output=True,timeout=10)
    assert result.stdout.strip().startswith('{'),result.stderr
    return result,json.loads(result.stdout)


def test_doctor_explains_missing_setup_without_creating_database(tmp_path):
    r,d=run_doctor(tmp_path,'APP_ENV=development\n')
    assert r.returncode==2 and d['status']=='blocked'
    assert d['network_calls']==0 and d['inference_requests']==0
    assert not (tmp_path/'data').exists()
    assert {'provider','stable_pepper','token','rpc'} <= {x['id'] for x in d['checks'] if x['status']=='blocked'}


def test_doctor_never_prints_invalid_private_values(tmp_path):
    secret='DO_NOT_DISCLOSE_987SECRET'
    r,d=run_doctor(tmp_path,f'MIN_HOLDING_RAW={secret}\nOPENBROKER_API_KEY=obk-{secret}\n')
    assert r.returncode==2
    assert secret not in r.stdout+r.stderr
    assert d['status']=='blocked'


def test_doctor_does_not_call_configured_services(tmp_path):
    text='''APP_ENV=development
KEY_PEPPER=0123456789abcdef0123456789abcdef
ADMIN_API_KEY=admin-secret-0123456789abcdefghijklmnop
OPENBROKER_API_KEY=obk-PRIVATE-UPSTREAM-SECRET
ACCESS_MODE=holder_allowance
HOLDER_MINT=So11111111111111111111111111111111111111112
MIN_HOLDING_RAW=1000
SOLANA_RPC_URL=https://example.invalid/PRIVATE-RPC-SECRET
'''
    r,d=run_doctor(tmp_path,text)
    assert r.returncode==0,r.stderr
    assert d['status']=='review_required' and not d['launch_authorized']
    assert 'PRIVATE-UPSTREAM' not in r.stdout and 'PRIVATE-RPC' not in r.stdout
    assert not (tmp_path/'data').exists()


def test_doctor_bad_environment_syntax_is_redacted(tmp_path):
    r,d=run_doctor(tmp_path,'this is not a config SECRET-VALUE\n')
    assert r.returncode==2 and 'SECRET-VALUE' not in r.stdout+r.stderr
    assert d['checks'][0]['id']=='environment_syntax'
