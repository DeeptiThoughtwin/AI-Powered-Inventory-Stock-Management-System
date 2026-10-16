import { useState } from "react";
import { useApi } from "../hooks";
import { Status, Card, when } from "../ui";

const asList = (d) => (Array.isArray(d) ? d : d ? Object.values(d).find(Array.isArray) || [] : []);

export default function History() {
  const [productId, setProductId] = useState("");
  const products = useApi("/products?include_inactive=true");
  const moves = useApi(productId ? `/products/${productId}/movements` : "/movements");

  const product = (products.data || []).find((p) => String(p.id) === productId);
  const rows = asList(moves.data);
  const qty = (m) => Number(m.quantity_change ?? m.change ?? m.quantity ?? 0);
  const net = rows.reduce((sum, m) => sum + qty(m), 0);
  const nameOf = (id) => (products.data || []).find((p) => p.id === id)?.name || `#${id}`;

  return (
    <div>
      <h1>Inventory history</h1>
      <div className="panel">
        <div className="row">
          <label className="field">Product
            <select value={productId} onChange={(e) => setProductId(e.target.value)}>
              <option value="">All products</option>
              {(products.data || []).map((p) => <option key={p.id} value={p.id}>{p.name} ({p.sku})</option>)}
            </select>
          </label>
        </div>

        {product && (
          <div className="cards">
            <Card label="Current stock" value={product.current_stock} />
            <Card label="Net of all movements" value={net} warn={net !== product.current_stock} />
          </div>
        )}
        {product && net !== product.current_stock && (
          <p className="error">Stock does not match the sum of movements. This needs investigating.</p>
        )}
        {product && net === product.current_stock && (
          <p className="muted">Current stock equals the sum of all movements below.</p>
        )}

        <Status loading={moves.loading} error={moves.error} />
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Date</th>{!productId && <th>Product</th>}<th>Type</th><th className="right">Change</th><th>Reference</th><th>Reason</th></tr>
            </thead>
            <tbody>
              {rows.map((m, i) => {
                const q = qty(m);
                return (
                  <tr key={m.id ?? i}>
                    <td>{when(m.created_at ?? m.date ?? m.timestamp)}</td>
                    {!productId && <td>{m.product_name || m.name || nameOf(m.product_id)}</td>}
                    <td>{m.movement_type ?? m.type}</td>
                    <td className="right"><span className={`badge ${q >= 0 ? "green" : "red"}`}>{q > 0 ? `+${q}` : q}</span></td>
                    <td>{m.reference ?? m.reference_id ?? "-"}</td>
                    <td>{m.reason || "-"}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
        {!moves.loading && !moves.error && rows.length === 0 && <p className="muted">No movements recorded.</p>}
        {/* <details><summary className="muted">Show raw response</summary>
          <pre style={{ overflow: "auto", maxHeight: 200 }}>{JSON.stringify(rows.slice(0, 2), null, 2)}</pre>
        </details> */}
      </div>
    </div>
  );
}