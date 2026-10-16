import { useState } from "react";
import { api } from "../api";
import { useApi } from "../hooks";
import { Status, money, when } from "../ui";

const EMPTY_LINE = { product_id: "", quantity: "1", price: "" };

export default function Transactions({ kind }) {
  const isSale = kind === "sale";
  const products = useApi("/products");
  const suppliers = useApi("/suppliers");
  const history = useApi(isSale ? "/sales-history" : "/purchases-history");

  const [supplierId, setSupplierId] = useState("");
  const [lines, setLines] = useState([{ ...EMPTY_LINE }]);
  const [message, setMessage] = useState({ type: "", text: "" });
  const [saving, setSaving] = useState(false);

  const productList = products.data || [];
  const updateLine = (i, patch) => setLines(lines.map((l, idx) => (idx === i ? { ...l, ...patch } : l)));

  function pickProduct(i, id) {
    const p = productList.find((x) => String(x.id) === id);
    updateLine(i, { product_id: id, price: p ? String(isSale ? p.selling_price : p.purchase_price) : "" });
  }

  const estimate = lines.reduce((sum, l) => sum + Number(l.quantity || 0) * Number(l.price || 0), 0);

  async function submit(e) {
    e.preventDefault();
    setMessage({ type: "", text: "" });
    setSaving(true);
    const items = lines.map((l) => ({
      product_id: Number(l.product_id),
      quantity: Number(l.quantity),
      [isSale ? "unit_price" : "unit_cost"]: Number(l.price),
    }));
    const body = isSale ? { items } : { supplier_id: Number(supplierId), items };
    try {
      const res = await api(isSale ? "/sales-bulk" : "/purchases-bulk", { method: "POST", body });
      setMessage({ type: "ok", text: `Recorded ${res.reference}. Total: ${money(res.total_amount)}` });
      setLines([{ ...EMPTY_LINE }]);
      history.reload();
      products.reload();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setSaving(false);
    }
  }

  return (
    <div>
      <h1>{isSale ? "Sales" : "Purchases"}</h1>

      <form className="panel" onSubmit={submit}>
        <h2>{isSale ? "Record a sale" : "Record a purchase"}</h2>
        {!isSale && (
          <div className="row">
            <label className="field">Supplier
              <select required value={supplierId} onChange={(e) => setSupplierId(e.target.value)}>
                <option value="">Choose supplier</option>
                {(suppliers.data || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
            </label>
          </div>
        )}
        {lines.map((l, i) => {
          const p = productList.find((x) => String(x.id) === l.product_id);
          return (
            <div className="row" key={i}>
              <label className="field">Product
                <select required value={l.product_id} onChange={(e) => pickProduct(i, e.target.value)}>
                  <option value="">Choose product</option>
                  {productList.map((x) => <option key={x.id} value={x.id}>{x.name} ({x.sku})</option>)}
                </select>
              </label>
              <label className="field">Quantity
                <input required type="number" min="1" step="1" value={l.quantity} onChange={(e) => updateLine(i, { quantity: e.target.value })} />
              </label>
              <label className="field">{isSale ? "Unit price" : "Unit cost"}
                <input required type="number" min="0" step="0.01" value={l.price} onChange={(e) => updateLine(i, { price: e.target.value })} />
              </label>
              {isSale && p && <span className="muted">In stock: {p.current_stock}</span>}
              {lines.length > 1 && (
                <button type="button" className="small" onClick={() => setLines(lines.filter((_, idx) => idx !== i))}>Remove</button>
              )}
            </div>
          );
        })}
        <button type="button" className="small" onClick={() => setLines([...lines, { ...EMPTY_LINE }])}>+ Add another product</button>
        <p>Estimated total: <b>{money(estimate)}</b> <span className="muted">(the server calculates the final total)</span></p>
        <button className="primary" type="submit" disabled={saving}>{saving ? "Saving..." : isSale ? "Confirm sale" : "Confirm purchase"}</button>
        {message.text && <p className={message.type}>{message.text}</p>}
      </form>

      <div className="panel">
        <h2>Transaction history</h2>
        <Status loading={history.loading} error={history.error} />
        <div className="scroll">
          <table>
            <thead>
              <tr><th>Reference</th><th>Date</th>{!isSale && <th>Supplier</th>}<th>Items</th><th className="right">Total</th></tr>
            </thead>
            <tbody>
              {(history.data || []).map((t) => (
                <tr key={t.reference}>
                  <td>{t.reference}</td>
                  <td>{when(t.date)}</td>
                  {!isSale && <td>{t.supplier}</td>}
                  <td>
                    {t.lines.map((l, i) => (
                      <div key={i}>{l.product_name} x {l.quantity} @ {money(isSale ? l.unit_price : l.unit_cost)}</div>
                    ))}
                  </td>
                  <td className="right">{money(t.total_amount)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}