"""Dựng source challenge đúng SHA đã audit, không sửa checkout của người dùng."""
from pathlib import Path
import subprocess
import json
import tarfile
import io

root = Path(__file__).resolve().parents[1]
repo = root / 'upstream/twelve-dollar-server-challenge'
url = 'https://github.com/arjaythedev/twelve-dollar-server-challenge.git'
def git(*args):
    return subprocess.check_output(['git', '-C', str(repo), *args], text=True).strip()
if not repo.exists():
    repo.parent.mkdir(exist_ok=True)
    subprocess.run(['git', 'clone', url, str(repo)], check=True)
if git('remote', 'get-url', 'origin') != url:
    raise SystemExit('origin không khớp repo challenge; dừng để tránh dùng nhầm source')
subprocess.run(['git', '-C', str(repo), 'fetch', 'origin', '+refs/pull/*/head:refs/remotes/origin/pr/*'], check=True)
rows = json.loads((root / 'evidence/pr-manifest.json').read_text())
for row in rows:
    sha = row['sha']
    subprocess.run(['git', '-C', str(repo), 'cat-file', '-e', sha + '^{commit}'], check=True)
    target = root / 'snapshots' / ('pr-' + str(row['pr']))
    marker = target / '.audit-sha'
    if target.exists():
        if marker.exists() and marker.read_text().strip() == sha:
            continue
        raise SystemExit(f'{target}: đã tồn tại nhưng không có marker đúng SHA; giữ nguyên, hãy dùng clone sạch')
    data = subprocess.check_output(['git', '-C', str(repo), 'archive', sha, 'submissions'])
    target.mkdir(parents=True)
    with tarfile.open(fileobj=io.BytesIO(data)) as archive:
        archive.extractall(target, filter='data')
    marker.write_text(sha + '\n')
print(f'Đã dựng {len(rows)} snapshot theo manifest; không checkout/pull đè thay đổi local.')
