// Fixture cố ý sai kiểu: runtime Bun vẫn chạy, compiler phải báo lỗi.
const value: number = "runtime string";
console.log(JSON.stringify({ value, runtimeType: typeof value }));
export {};
