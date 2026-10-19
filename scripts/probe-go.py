"""Chạy parser/auth nguyên bản PR111 trong fixture cục bộ, không mở socket."""
import json
import os
from pathlib import Path
import subprocess
import tempfile

root = Path(__file__).resolve().parents[1]
source = root / 'snapshots/pr-111/submissions/go-epoll-brady1408'
test = r'''package main
import (
 "testing"
 "fmt"
 "crypto/hmac"
 "crypto/sha256"
 "encoding/base64"
)
func TestAuditFixture(t *testing.T) {
 req,n,st:=parseRequest([]byte("POST /posts HTTP/1.1\r\nHost: x\r\nContent-Length: 999\r\nContent-Length: 2\r\n\r\n{}"))
 fmt.Printf("duplicate_CL status=%d consumed=%d body=%q\n",st,n,req.body)
 header:=base64.RawURLEncoding.EncodeToString([]byte(`{"alg":"HS256"}`))
 payload:=base64.RawURLEncoding.EncodeToString([]byte(`{"sub":"1","username":"fixture","exp":2000000000,"nbf":1900000000}`))
 signed:=header+"."+payload
 key:=[]byte("local-audit-fixture")
 mac:=hmac.New(sha256.New,key);mac.Write([]byte(signed))
 token:=signed+"."+base64.RawURLEncoding.EncodeToString(mac.Sum(nil))
 user,status:=newVerifier(key).authenticate([]byte("Bearer "+token),1800000000)
 fmt.Printf("future_nbf auth_status=%d user=%d\n",status,user.userID)
}
'''
with tempfile.TemporaryDirectory() as directory:
    target = Path(directory)
    for name in ['auth.go', 'http.go']:
        (target / name).write_bytes((source / name).read_bytes())
    (target / 'audit_test.go').write_text(test)
    environment = dict(os.environ, GO111MODULE='off', GOTOOLCHAIN='local')
    completed = subprocess.run(['go','test','-v'], cwd=directory, env=environment, capture_output=True, text=True, check=True)
print(json.dumps({'boundary':'original auth.go/http.go in isolated test, no full HTTP server', 'go':subprocess.check_output(['go','version'],text=True).strip(), 'output':completed.stdout},indent=2))
