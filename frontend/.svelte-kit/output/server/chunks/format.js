function formatTime(seconds) {
  if (!isFinite(seconds) || seconds < 0) return "00:00";
  const h = Math.floor(seconds / 3600);
  const m = Math.floor(seconds % 3600 / 60);
  const s = Math.floor(seconds % 60);
  const mm = String(m).padStart(2, "0");
  const ss = String(s).padStart(2, "0");
  if (h > 0) return `${String(h).padStart(2, "0")}:${mm}:${ss}`;
  return `${mm}:${ss}`;
}
function formatSize(bytes) {
  if (!bytes || bytes === 0) return "0 B";
  const units = ["B", "KB", "MB", "GB", "TB"];
  const i = Math.min(Math.floor(Math.log(bytes) / Math.log(1024)), units.length - 1);
  const size = bytes / Math.pow(1024, i);
  return `${size.toFixed(size >= 10 || i === 0 ? 0 : 1)} ${units[i]}`;
}
function formatDate(date) {
  const d = typeof date === "string" ? new Date(date) : date;
  if (isNaN(d.getTime())) return "--";
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}
function formatNumber(n) {
  return n.toLocaleString("zh-CN");
}
function formatResolution(width, height) {
  if (!width || !height) return "--";
  return `${width} × ${height}`;
}
export {
  formatNumber as a,
  formatSize as b,
  formatResolution as c,
  formatDate as d,
  formatTime as f
};
