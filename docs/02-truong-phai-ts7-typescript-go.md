# TS7 viết bằng Go: compiler nhanh và runtime là hai phép đo

## Kết luận

TS7 kiểm kiểu/emit/build/editor; Bun chạy JavaScript sau khi xử lý cú pháp TS. Dùng cả hai được,
nhưng compiler nhanh không làm request tự nhanh hơn. Một Bun app chạy trực tiếp `.ts` không
gọi `tsc` trước mỗi request. Cú pháp mới vẫn phải được runtime hỗ trợ; không đúng khi nói Bun
không bao giờ quan tâm phiên bản TS.

## Luồng source đã đọc

Snapshot `microsoft/typescript-go` SHA `89d5d5b2849a0db0957065889ca58536fa6d2e4a`:

1. `cmd/tsgo/main.go`: CLI → chọn LSP/API hoặc execute.CommandLine.
2. `internal/execute/tsc.go`: phân nhánh compile thường và build project references.
3. `internal/compiler/fileloader.go`: tải/resolve files với WorkGroup.
4. `internal/parser/parser.go:135`: ParseSourceFile, tạo AST; đây là code compiler chạy khi build.
5. `internal/compiler/checkerpool.go:305`: pool mặc định 4 checker, singleThreaded về 1, clamp theo số file và giới hạn; checker có lock/association theo file.
6. `internal/compiler/program.go:669`: nhóm files theo checker để giảm contention/cache misses; diagnostics hợp nhất/sort; emit là bước riêng.
7. `internal/core/workgroup.go`: đường parallel dùng goroutine/WaitGroup; đường single giữ việc tuần tự.

Đã đọc các điểm điều phối này, chưa audit từng quy tắc trong checker, toàn bộ LSP/watch và mọi dependency.
Snapshot archive có thể khác compiler npm phát hành. Source có --api không chứng minh API đó là hợp đồng public ổn định.

Lợi ích có cơ sở: native execution, song song hóa và tổ chức công việc/cache locality. Không có số đo ở đây
để quy bao nhiêu phần trăm cho GC, struct hay allocation; tránh khẳng định “GC rẻ hơn nhiều” chỉ từ việc đổi ngôn ngữ.
Launcher npm được đọc dùng Node execve/execFileSync để gọi executable: “không startup Node” không đúng với mọi đường gọi.

## Nguồn và phiên bản

[Repo archive](https://github.com/microsoft/typescript-go) hướng về
[TypeScript chính](https://github.com/microsoft/TypeScript).
[Thông báo TS7](https://devblogs.microsoft.com/typescript/announcing-typescript-7-0/) mô tả defaults,
parallelism và giới hạn API thời điểm 7.0; số nhanh hơn do Microsoft công bố là số của họ, chưa đo lại.
[Bun TypeScript](https://bun.com/docs/runtime/typescript) hướng dẫn types bun và bundler resolution.
Không coi lịch 7.1 hoặc trạng thái từng tool trong bài pasted là hiện trạng đã kiểm chứng.

## Cấu hình và migration

Pin compiler/runtime/typings, khai báo types bun, module Preserve, resolution bundler, strict và noEmit
như `labs/toolchain/tsconfig.json`. Với service Node phải chọn resolution/module theo deployment Node.
TS7 đổi defaults và bỏ một số config cũ; nâng theo diagnostic thực. Tool dùng compiler API cần
kiểm từng version: alias TS6 có thể giữ API cũ, nhưng 7.1 xuất hiện không tự làm mọi integration tương thích.

## Bằng chứng local đang có

`evidence/toolchain-probes.json` từ lượt trước mang nhãn ts7 nhưng stdout tsc và tsc6 đều là
**Version 6.0.3** dù manifest yêu cầu 7.0.2/6.0.2. Vì thế chưa xác nhận native TS7 thực chạy.
Fixture chứng minh Bun trả HTTP200 với SQLite42 và vẫn chạy biến sai annotation; compiler báo TS2322.
Không dùng fixture nhỏ này để tuyên bố build tăng tốc hoặc TS7/Bun thắng stack khác.
Script probe đã bổ sung kiểm version để chặn nhãn sai ở lần chạy tiếp.

## Thí nghiệm tiếp theo

Xác minh executable version/origin → typecheck cùng project TS6/TS7 → so diagnostic và declaration emit
→ đo cold/warm/incremental/build/watch riêng → ghi CPU/RAM/checkers/builders. Runtime Node/Bun/Go
đo riêng cùng API/SQL/durability. Chỉ chọn TS7+Bun khi tooling tương thích và số đo ứng dụng đạt SLO.
