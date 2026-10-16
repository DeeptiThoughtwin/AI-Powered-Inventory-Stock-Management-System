import { useState } from "react";
import { api } from "../api";
import { useApi } from "../hooks";
import { Status, Card, Bars, money } from "../ui";

function query(filters) {
  const p = new URLSearchParams();
  Object.entries(filters).forEach(([k, v]) => {
    if (v) p.set(k, v);
  });
  const s = p.toString();
  return s ? `?${s}` : "";
}

export default function Dashboard() {
  const [filters, setFilters] = useState({ start_date: "", end_date: "", category: "", product_id: "" });
  const [ai, setAi] = useState(null);
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");
  const q = query(filters);

  const summary = useApi("/analytics/summary");
  const low = useApi("/alerts/low-stock");
  const products = useApi("/products?include_inactive=true");
  const suppliers = useApi("/suppliers");
  const sales = useApi(`/analytics/sales-summary${q}`);
  const trend = useApi(`/analytics/sales-trend${q}`);
  const best = useApi(`/analytics/best-selling${q}`);
  const slow = useApi(`/analytics/slow-moving${q}`);
  const insights = useApi("/insights");

  const set = (key) => (e) => setFilters({ ...filters, [key]: e.target.value });
  const categories = [...new Set((products.data || []).map((p) => p.category).filter(Boolean))];
  const supplierName = (id) => (suppliers.data || []).find((s) => s.id === id)?.name || "No supplier";
  const s = summary.data;

  async function generateAi() {
    setAiLoading(true);
    setAiError("");
    try {
      setAi(await api("/insights/ai", { method: "POST" }));
    } catch (e) {
      setAiError(e.message);
    } finally {
      setAiLoading(false);
    }
  }

  return (
    <div>
      <h1>Dashboard</h1>
      <Status loading={summary.loading} error={summary.error} />
      <div className="cards">
        <Card label="Products" value={s?.total_products ?? "-"} />
        <Card label="Units in stock" value={s?.total_units_in_stock ?? "-"} />
        <Card label="Inventory cost value" value={s ? money(s.inventory_cost_value) : "-"} />
        <Card label="Inventory retail value" value={s ? money(s.inventory_retail_value) : "-"} />
        <Card label="Low-stock products" value={s?.low_stock_count ?? "-"} warn={s?.low_stock_count > 0} />
      </div>

      <div className="panel">
        <h2>Low-stock alerts</h2>
        <Status loading={low.loading} error={low.error} />
        {low.data?.total_alerts === 0 && <p className="muted">All products are above their minimum stock.</p>}
        {low.data?.total_alerts > 0 && (
          <table>
            <thead>
              <tr><th>Product</th><th>SKU</th><th className="right">In stock</th><th className="right">Minimum</th><th>Status</th><th>Supplier</th></tr>
            </thead>
            <tbody>
              {low.data.products.map((p) => (
                <tr key={p.id}>
                  <td>{p.name}</td><td>{p.sku}</td>
                  <td className="right">{p.current_stock}</td>
                  <td className="right">{p.minimum_stock}</td>
                  <td>
                    {p.current_stock <= 0
                      ? <span className="badge red">Out of stock</span>
                      : <span className="badge amber">Low stock</span>}
                  </td>
                  <td>{supplierName(p.supplier_id)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
        <p className="muted">To replenish, open "Forecast & reorder" and approve a purchase order.</p>
      </div>

      <div className="panel">
        <h2>Sales analytics</h2>
        <div className="row">
          <label className="field">From<input type="date" value={filters.start_date} onChange={set("start_date")} /></label>
          <label className="field">To<input type="date" value={filters.end_date} onChange={set("end_date")} /></label>
          <label className="field">Category
            <select value={filters.category} onChange={set("category")}>
              <option value="">All</option>
              {categories.map((c) => <option key={c} value={c}>{c}</option>)}
            </select>
          </label>
          <label className="field">Product
            <select value={filters.product_id} onChange={set("product_id")}>
              <option value="">All</option>
              {(products.data || []).map((p) => <option key={p.id} value={p.id}>{p.name}</option>)}
            </select>
          </label>
          <button className="small" onClick={() => setFilters({ start_date: "", end_date: "", category: "", product_id: "" })}>Clear</button>
        </div>
        <Status loading={sales.loading} error={sales.error} />
        <div className="cards">
          <Card label="Total sales" value={sales.data ? money(sales.data.total_sales_amount) : "-"} />
          <Card label="Units sold" value={sales.data?.total_units_sold ?? "-"} />
          <Card label="Transactions" value={sales.data?.total_transactions ?? "-"} />
        </div>
        <h2>Sales trend (amount per day)</h2>
        <Status loading={trend.loading} error={trend.error} />
        {trend.data && <Bars rows={trend.data} labelKey="date" valueKey="sales_amount" />}
      </div>

      <div className="grid2">
        <div className="panel">
          <h2>Best-selling products</h2>
          <Status loading={best.loading} error={best.error} />
          <table>
            <thead><tr><th>Product</th><th className="right">Units</th><th className="right">Revenue</th></tr></thead>
            <tbody>
              {(best.data || []).map((b) => (
                <tr key={b.product_id}><td>{b.name}</td><td className="right">{b.units_sold}</td><td className="right">{money(b.revenue)}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
        <div className="panel">
          <h2>Slow-moving products</h2>
          <Status loading={slow.loading} error={slow.error} />
          <table>
            <thead><tr><th>Product</th><th className="right">Units sold</th><th className="right">In stock</th></tr></thead>
            <tbody>
              {(slow.data || []).map((b) => (
                <tr key={b.product_id}><td>{b.name}</td><td className="right">{b.units_sold}</td><td className="right">{b.current_stock}</td></tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>

      <div className="panel">
        <h2>Inventory insights</h2>
        <Status loading={insights.loading} error={insights.error} />
        <ul>
          {(insights.data?.insights || []).map((i) => (
            <li key={i.title}><b>{i.title}:</b> {i.text}</li>
          ))}
        </ul>
        <p className="muted">These lines are built only from the calculated numbers above.</p>
        <button className="primary" onClick={generateAi} disabled={aiLoading}>
          {aiLoading ? "Generating..." : "Generate AI summary"}
        </button>
        {aiError && <p className="error">{aiError}</p>}
        
        {/* Updated Document-Style AI Response Container */}
        {ai && (
          <div style={{
            background: "#ffffff",
            border: "1px solid #cbd5e1",
            borderTop: "3px solid #312e81",
            borderRadius: "6px",
            padding: "20px 24px",
            fontFamily: "system-ui, -apple-system, sans-serif",
            fontSize: "14px",
            color: "#0f172a",
            lineHeight: "1.7",
            whiteSpace: "pre-wrap",
            marginTop: "16px",
            boxShadow: "0 2px 4px rgba(0, 0, 0, 0.02)"
          }}>
            {ai.summary}
          </div>
        )}
      </div>
    </div>
  );
}