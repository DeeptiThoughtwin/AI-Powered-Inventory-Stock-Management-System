import { useEffect, useState } from "react";
import { api } from "../api";
import { useApi } from "../hooks";
import { Status, Bars, when } from "../ui";

export default function Forecast() {
  const [horizon, setHorizon] = useState("7");
  const [historyDays, setHistoryDays] = useState("30");
  const [windowDays, setWindowDays] = useState("7");

  const products = useApi("/products");
  const rec = useApi("/reorder/recommendations");
  const orders = useApi("/purchase-orders");

  const [forecasts, setForecasts] = useState({});
  const [fLoading, setFLoading] = useState(false);
  const [fError, setFError] = useState("");

  const [selectedId, setSelectedId] = useState(null);
  const [explain, setExplain] = useState({});
  const [explainBusy, setExplainBusy] = useState(null);
  const [busyId, setBusyId] = useState(null);
  const [message, setMessage] = useState({ type: "", text: "" });

  const productList = products.data || [];
  const recRows = rec.data?.recommendations || [];
  const orderList = Array.isArray(orders.data) ? orders.data : [];

  // Units already on approved purchase orders, per product
  const incoming = {};
  orderList.filter((o) => o.status === "approved").forEach((o) => {
    incoming[o.product_id] = (incoming[o.product_id] || 0) + o.quantity;
  });

  const qs = `history_days=${historyDays}&window=${windowDays}&horizon_days=${horizon}`;

  // Load a forecast for every active product
  useEffect(() => {
    const list = productList.filter((p) => p.is_active !== false);
    if (list.length === 0) {
      setForecasts({});
      return;
    }
    let cancelled = false;
    setFLoading(true);
    setFError("");
    Promise.all(list.map((p) => api(`/analytics/forecast/${p.id}?${qs}`).then((f) => [p.id, f])))
      .then((entries) => { if (!cancelled) setForecasts(Object.fromEntries(entries)); })
      .catch((e) => { if (!cancelled) setFError(e.message); })
      .finally(() => { if (!cancelled) setFLoading(false); });
    return () => { cancelled = true; };
  }, [products.data, horizon, historyDays, windowDays]); // eslint-disable-line

  async function explainProduct(id) {
    setSelectedId(id);
    setExplainBusy(id);
    try {
      const res = await api(`/analytics/forecast/${id}/explain?${qs}`, { method: "POST" });
      setExplain((prev) => ({ ...prev, [id]: res.explanation }));
    } catch (err) {
      setExplain((prev) => ({ ...prev, [id]: `Error: ${err.message}` }));
    } finally {
      setExplainBusy(null);
    }
  }

  async function approve(r) {
    setBusyId(r.product_id);
    setMessage({ type: "", text: "" });
    try {
      await api("/purchase-orders", {
        method: "POST",
        body: { product_id: r.product_id, supplier_id: r.supplier_id, quantity: r.recommended_quantity },
      });
      setMessage({ type: "ok", text: `Purchase order approved for ${r.name}: ${r.recommended_quantity} units.` });
      rec.reload();
      orders.reload();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setBusyId(null);
    }
  }

  function stockBadge(p, f) {
    const expected = p.current_stock + (incoming[p.id] || 0) - f.predicted_total_demand;
    if (expected < 0) return <span className="badge red">May run out</span>;
    if (expected <= p.minimum_stock) return <span className="badge amber">Low soon</span>;
    return <span className="badge green">OK</span>;
  }

  const selected = productList.find((p) => p.id === selectedId);
  const selectedForecast = selectedId ? forecasts[selectedId] : null;
  const nameOf = (id) => productList.find((p) => p.id === id)?.name || `#${id}`;

  return (
    <div style={{ display: "flex", flexDirection: "column", gap: "16px", paddingBottom: "32px" }}>
      <h1 style={{ marginBottom: "0px" }}>Forecast & reorder</h1>

      <div className="panel" style={{ padding: "18px 22px", marginBottom: "0px" }}>
        <h2 style={{ marginTop: "0px", marginBottom: "6px" }}>Demand forecast</h2>
        <p className="muted" style={{ marginBottom: "14px" }}>
          Predicts how many units each product may sell using a moving average of recent daily sales.
        </p>
        <div className="row" style={{ marginBottom: "16px", gap: "12px" }}>
          <label className="field">Forecast period
            <select value={horizon} onChange={(e) => setHorizon(e.target.value)}>
              <option value="7">Next 7 days</option>
              <option value="15">Next 15 days</option>
              <option value="30">Next 30 days</option>
            </select>
          </label>
          <label className="field">History used
            <select value={historyDays} onChange={(e) => setHistoryDays(e.target.value)}>
              <option value="30">Last 30 days</option>
              <option value="60">Last 60 days</option>
              <option value="90">Last 90 days</option>
            </select>
          </label>
          <label className="field">Moving average
            <select value={windowDays} onChange={(e) => setWindowDays(e.target.value)}>
              <option value="7">7-day average</option>
              <option value="14">14-day average</option>
            </select>
          </label>
        </div>
        <Status loading={products.loading || fLoading} error={products.error || fError} />

        <div className="scroll" style={{ marginTop: "8px" }}>
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th className="right">In stock</th>
                <th className="right">On order</th>
                <th className="right">Predicted / day</th>
                <th className="right">Demand ({horizon} days)</th>
                <th className="right">Expected stock</th>
                <th>History used</th>
                <th className="right">Avg error / day</th>
                <th>Status</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {productList.filter((p) => forecasts[p.id]).map((p) => {
                const f = forecasts[p.id];
                const expected = p.current_stock + (incoming[p.id] || 0) - f.predicted_total_demand;
                return (
                  <tr key={p.id}>
                    <td>{p.name}</td>
                    <td className="right">{p.current_stock}</td>
                    <td className="right">{incoming[p.id] || 0}</td>
                    <td className="right">{f.predicted_daily_demand.toFixed(2)}</td>
                    <td className="right">{f.predicted_total_demand}</td>
                    <td className="right"><b>{Math.round(expected * 10) / 10}</b></td>
                    <td className="muted">last {historyDays} days, {f.window_days}-day avg</td>
                    <td className="right">{f.average_error_units_per_day ?? "-"}</td>
                    <td>{stockBadge(p, f)}</td>
                    <td style={{ whiteSpace: "nowrap" }}>
                      <button className="small" onClick={() => setSelectedId(p.id)} style={{ marginRight: "4px" }}>Details</button>
                      <button className="small" disabled={explainBusy === p.id} onClick={() => explainProduct(p.id)}>
                        {explainBusy === p.id ? "Explaining..." : "Explain with AI"}
                      </button>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        <p className="muted" style={{ marginTop: "12px", marginBottom: "0px", fontSize: "12px" }}>
          * Expected stock = current stock + units on approved orders - predicted demand for the period.
        </p>
      </div>

      {selected && selectedForecast && (
        <div className="panel" style={{ padding: "18px 22px", marginBottom: "0px", borderLeft: "4px solid #4f46e5" }}>
          <h2 style={{ marginTop: "0px", marginBottom: "4px" }}>{selected.name}: details</h2>
          <p className="muted" style={{ marginBottom: "16px" }}>
            History period: {selectedForecast.history[0]?.date} to {selectedForecast.history.at(-1)?.date}.
            Forecast for the next {selectedForecast.horizon_days} days: about {selectedForecast.predicted_daily_demand} units per day.
          </p>
          <div className="grid2" style={{ gap: "16px", marginBottom: "16px" }}>
            <div>
              <h3 style={{ fontSize: "14px", marginBottom: "8px" }}>Actual units sold per day</h3>
              <Bars rows={selectedForecast.history} labelKey="date" valueKey="actual_units" />
            </div>
            <div>
              <h3 style={{ fontSize: "14px", marginBottom: "8px" }}>Forecast units per day</h3>
              <Bars
                rows={[
                  ...selectedForecast.history.filter((h) => h.forecast_units !== null),
                  ...selectedForecast.future,
                ]}
                labelKey="date"
                valueKey="forecast_units"
              />
            </div>
          </div>
          
          <h3 style={{ fontSize: "15px", marginBottom: "6px" }}>Plain-language explanation</h3>
          {explainBusy === selectedId && <p className="muted">Generating AI report...</p>}
          
          {explain[selectedId] && (
            <div style={{
              background: "#ffffff",
              border: "1px solid #cbd5e1",
              borderTop: "3px solid #312e81",
              borderRadius: "6px",
              padding: "16px 20px",
              fontFamily: "system-ui, -apple-system, sans-serif",
              fontSize: "14px",
              color: "#0f172a",
              lineHeight: "1.6",
              whiteSpace: "pre-wrap",
              marginTop: "8px",
              marginBottom: "12px",
              boxShadow: "0 1px 3px rgba(0,0,0,0.02)"
            }}>
              {explain[selectedId]}
            </div>
          )}

          {!explain[selectedId] && explainBusy !== selectedId && (
            <button className="primary" onClick={() => explainProduct(selectedId)}>Explain with AI</button>
          )}
        </div>
      )}

      <div className="panel" style={{ padding: "18px 22px", marginBottom: "0px" }}>
        <h2 style={{ marginTop: "0px", marginBottom: "6px" }}>Reorder recommendations</h2>
        <p className="muted" style={{ marginBottom: "12px" }}>
          Recommended when expected demand during delivery time plus safety stock exceeds current inventory.
        </p>
        <Status loading={rec.loading} error={rec.error} />
        {message.text && <p className={message.type}>{message.text}</p>}
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Product</th>
                <th className="right">In stock</th>
                <th className="right">Avg / day</th>
                <th className="right">Lead time</th>
                <th className="right">Safety stock</th>
                <th className="right">Suggested order</th>
                <th>Supplier</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              {recRows.map((r) => (
                <tr key={r.product_id}>
                  <td>
                    <b>{r.name}</b>
                    <div className="muted" style={{ fontSize: "12px", marginTop: "2px" }}>{r.explanation}</div>
                  </td>
                  <td className="right">{r.current_stock}</td>
                  <td className="right">{Number(r.avg_daily_demand ?? 0).toFixed(1)}</td>
                  <td className="right">{r.lead_time_days} d</td>
                  <td className="right">{r.safety_stock}</td>
                  <td className="right"><b>{r.recommended_quantity}</b></td>
                  <td>
                    {r.needs_supplier
                      ? <span className="badge amber">Needs supplier</span>
                      : <span className="badge green">{r.supplier_name}</span>}
                  </td>
                  <td>
                    <button className="small" disabled={r.needs_supplier || busyId === r.product_id}
                            onClick={() => approve(r)}>
                      {busyId === r.product_id ? "Creating..." : "Approve order"}
                    </button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!rec.loading && !rec.error && recRows.length === 0 && (
          <p className="muted" style={{ marginTop: "10px", marginBottom: "0px" }}>
            No products need reordering right now. Stock levels are healthy.
          </p>
        )}
      </div>

      <div className="panel" style={{ padding: "18px 22px", marginBottom: "0px" }}>
        <h2 style={{ marginTop: "0px", marginBottom: "12px" }}>Approved purchase orders</h2>
        <Status loading={orders.loading} error={orders.error} />
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Order</th>
                <th>Product</th>
                <th className="right">Quantity</th>
                <th>Status</th>
                <th>Created</th>
              </tr>
            </thead>
            <tbody>
              {orderList.map((o) => (
                <tr key={o.id}>
                  <td>#{o.id}</td>
                  <td>{nameOf(o.product_id)}</td>
                  <td className="right">{o.quantity}</td>
                  <td><span className="badge green">{o.status}</span></td>
                  <td>{when(o.created_at)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!orders.loading && orderList.length === 0 && (
          <p className="muted" style={{ marginTop: "10px", marginBottom: "0px" }}>No purchase orders yet.</p>
        )}
      </div>
    </div>
  );
}