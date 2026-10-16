export function Status({ loading, error }) {
  if (loading) return <p className="muted">Loading...</p>;
  if (error) return <p className="error">{error}</p>;
  return null;
}

export function Card({ label, value, warn }) {
  return (
    <div className={`card ${warn ? "warn" : ""}`}>
      <div className="label">{label}</div>
      <div className="value">{value}</div>
    </div>
  );
}

export function Bars({ rows, labelKey, valueKey, height = 170 }) {
  if (!rows || rows.length === 0) {
    return <p className="muted">No data for this period.</p>;
  }
  const values = rows.map((r) => Number(r[valueKey]) || 0);
  const max = Math.max(1, ...values);
  const barArea = height - 18; // room for the number above each bar

  return (
    <div>
      <div
        style={{
          display: "flex",
          alignItems: "flex-end",
          gap: 4,
          height,
          borderBottom: "1px solid #d1d5db",
          overflowX: "auto",
        }}
      >
        {rows.map((r, i) => {
          const v = values[i];
          const h = v > 0 ? Math.max(4, Math.round((v / max) * barArea)) : 2;
          return (
            <div
              key={`${r[labelKey]}-${i}`}
              title={`${r[labelKey]}: ${v}`}
              style={{
                flex: "1 1 0",
                minWidth: 30,
                maxWidth: 70,
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                justifyContent: "flex-end",
              }}
            >
              <span style={{ fontSize: 10, color: "#374151", height: 14 }}>
                {v > 0 ? Math.round(v) : ""}
              </span>
              <div
                style={{
                  width: "100%",
                  height: h,
                  background: v > 0 ? "#3b82f6" : "#d1d5db",
                  borderRadius: "3px 3px 0 0",
                }}
              />
            </div>
          );
        })}
      </div>
      <div className="bars-caption">
        {rows.length} day(s): {rows[0][labelKey]} to {rows[rows.length - 1][labelKey]}. Hover a bar for details.
      </div>
    </div>
  );
}

export const money = (n) =>
  Number(n ?? 0).toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });

export const when = (d) => (d ? new Date(d).toLocaleString() : "");