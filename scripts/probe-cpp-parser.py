"""Biên dịch nguyên văn các hàm parser C++ được trích; không chạy server."""
from pathlib import Path
import subprocess
import tempfile
import json
root = Path(__file__).resolve().parents[1]
source = root / 'snapshots/pr-9/submissions/cpp-epoll_inmem-khalefa-ow/src/main.cpp'
text = source.read_text()
request = text[text.index('struct Request {'):text.index('\nint route(', text.index('struct Request {'))] if '\nint route(' in text else ''
# Lấy struct theo dấu đóng đầu tiên, các helper/parser theo ranh giới source.
start = text.index('struct Request {')
request = text[start:text.index('\n};', start) + 3]
helpers = text[text.index('bool ieq('):text.index('// ---------------------------------------------------------------------------------------------\n// connections')]
header = '#include <string>\n#include <string_view>\n#include <cstring>\n#include <cstdint>\n#include <cstdio>\n#include <sys/types.h>\nconstexpr size_t kMaxHeaderBytes=65536, kMaxBodyBytes=1048576;\n'
main = r'''
int main() {
 const char* cases[] = {
  "POST /posts HTTP/1.1\r\nHost: x\r\nContent-Length: 999\r\nContent-Length: 2\r\n\r\n{}",
  "POST /posts HTTP/1.1\r\nHost: x\r\nContent-Length: 999\r\nTransfer-Encoding: chunked\r\n\r\n0\r\n\r\n",
  "GET /feed HTTP/9.9\r\nHost: x\r\n\r\n"
 };
 for (auto input : cases) {
  Request req; size_t consumed=0; std::string chunked;
  auto p=parse_request(input,strlen(input),&req,&consumed,chunked);
  printf("%d %zu %zu\n",int(p),consumed,req.body.size());
 }
}
'''
with tempfile.TemporaryDirectory() as d:
 p=Path(d); (p/'probe.cpp').write_text(header+request+helpers+main)
 subprocess.run(['g++','-std=c++17','-O0',str(p/'probe.cpp'),'-o',str(p/'probe')],check=True)
 output=subprocess.check_output([str(p/'probe')],text=True)
print(json.dumps({'source':str(source.relative_to(root)), 'boundary':'extracted exact parser functions, not full server', 'enum':'kOk=0,kIncomplete=1,kBad=2', 'cases':['conflicting content-length','content-length and transfer-encoding','HTTP/9.9'], 'output':output},indent=2))
