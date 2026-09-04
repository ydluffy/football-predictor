export function getShanghaiToday(): string {
  const d = new Date(new Date().toLocaleString("en-US", { timeZone: "Asia/Shanghai" }));
  const yyyy = d.getFullYear();
  const mm = String(d.getMonth() + 1).padStart(2, "0");
  const dd = String(d.getDate()).padStart(2, "0");
  return `${yyyy}-${mm}-${dd}`;
}
