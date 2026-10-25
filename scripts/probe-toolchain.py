"""Chứng minh ranh giới Bun runtime và TS compiler; không phải benchmark tốc độ."""
from pathlib import Path
import json
import subprocess
import tempfile
import shutil

root = Path(__file__).resolve().parents[1]
lab = root / 'labs/toolchain'
bins = lab / 'node_modules/.bin'

def run(arguments, cwd=lab):
    result = subprocess.run([str(a) for a in arguments], cwd=cwd, capture_output=True, text=True, timeout=60)
    return {'command': [str(a).replace(str(root), '.') for a in arguments], 'exit_code': result.returncode,
            'stdout': result.stdout.strip(), 'stderr': result.stderr.strip()}

checks = {}
checks['ts7_version'] = run([bins/'tsc', '--version'])
checks['bun_version'] = run([bins/'bun', '--version'])
checks['ts6_version'] = run([bins/'tsc6', '--version'])
if checks['ts7_version']['stdout'] != 'Version 7.0.2' or checks['ts6_version']['stdout'] != 'Version 6.0.2':
    raise SystemExit(json.dumps({'error': 'Compiler version mismatch; cannot label this TS7 evidence', 'versions': checks}, indent=2))
checks['ts7_valid'] = run([bins/'tsc', '-p', 'tsconfig.json'])
checks['bun_valid'] = run([bins/'bun', 'run', 'valid.ts'])
checks['bun_invalid_type'] = run([bins/'bun', 'run', 'invalid.ts'])
with tempfile.TemporaryDirectory() as directory:
    fixture = Path(directory)
    shutil.copy(lab/'invalid.ts', fixture/'invalid.ts')
    (fixture/'tsconfig.json').write_text(json.dumps({'compilerOptions': {'strict': True, 'noEmit': True}, 'include': ['invalid.ts']}))
    checks['ts7_invalid_type'] = run([bins/'tsc', '-p', 'tsconfig.json'], cwd=fixture)
    checks['ts6_invalid_type'] = run([bins/'tsc6', '-p', 'tsconfig.json'], cwd=fixture)
assert checks['ts7_valid']['exit_code'] == 0, checks
assert checks['bun_valid']['exit_code'] == 0, checks
assert json.loads(checks['bun_valid']['stdout']) == {'status': 200, 'data': {'value': 42}}, checks
assert checks['bun_invalid_type']['exit_code'] == 0, checks
assert json.loads(checks['bun_invalid_type']['stdout'])['runtimeType'] == 'string', checks
assert checks['ts7_invalid_type']['exit_code'] != 0 and 'TS2322' in checks['ts7_invalid_type']['stdout'], checks
assert checks['ts6_invalid_type']['exit_code'] != 0 and 'TS2322' in checks['ts6_invalid_type']['stdout'], checks
print(json.dumps({'boundary': 'isolated Bun HTTP+SQLite fixture and compiler negative case; no throughput measurement', 'checks': checks}, indent=2, ensure_ascii=False))
