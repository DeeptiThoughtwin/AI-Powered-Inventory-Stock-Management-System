import { useState } from "react";
import { api } from "../api";
import { useApi } from "../hooks";
import { Status, money, when } from "../ui";

const EP = {
  list: "/suppliers",
  create: "/suppliers",
  update: (id) => `/suppliers/${id}`,
  remove: (id) => `/suppliers/${id}`,
  products: (id) => `/suppliers/${id}/products`,
  purchases: (id) => `/suppliers/${id}/purchases`,
};
const EMPTY = { name: "", contact_person: "", email: "", phone: "", address: "", lead_time_days: "7" };

export default function Suppliers() {
  const suppliers = useApi(EP.list);
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [selected, setSelected] = useState(null);
  const [message, setMessage] = useState({ type: "", text: "" });
  const [saving, setSaving] = useState(false);

  const products = useApi(selected ? EP.products(selected.id) : null);
  const purchases = useApi(selected ? EP.purchases(selected.id) : null);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });

  function edit(s) {
    setEditId(s.id);
    setForm({
      name: s.name, contact_person: s.contact_person || "", email: s.email || "",
      phone: s.phone || "", address: s.address || "", lead_time_days: String(s.lead_time_days ?? 7),
    });
    setMessage({ type: "", text: "" });
  }

  function reset() {
    setEditId(null);
    setForm(EMPTY);
  }

  async function submit(e) {
    e.preventDefault();
    setSaving(true);
    setMessage({ type: "", text: "" });
    const body = { ...form, lead_time_days: Number(form.lead_time_days) };
    try {
      await api(editId ? EP.update(editId) : EP.create, { method: editId ? "PUT" : "POST", body });
      setMessage({ type: "ok", text: editId ? "Supplier updated." : "Supplier created." });
      reset();
      suppliers.reload();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setSaving(false);
    }
  }

  async function remove(s) {
  setMessage({ type: "", text: "" });
  try {
    await api(EP.remove(s.id), { method: "DELETE" });
    setMessage({ type: "ok", text: `Supplier "${s.name}" deleted.` });
    if (selected && selected.id === s.id) setSelected(null);
    if (editId === s.id) reset();
    suppliers.reload();
  } catch (err) {
    // For example: "This supplier is linked to products or purchases and cannot be deleted."
    setMessage({ type: "error", text: err.message });
  }
}

  // The purchase history endpoint returns an object, not a plain list.
  const history = purchases.data?.purchases || [];

  return (
    <div>
      <h1>Suppliers</h1>

      <form className="panel" onSubmit={submit}>
        <h2>{editId ? "Edit supplier" : "Add supplier"}</h2>
        <div className="row">
          <label className="field">Company name<input required value={form.name} onChange={set("name")} /></label>
          <label className="field">Contact person<input value={form.contact_person} onChange={set("contact_person")} /></label>
          <label className="field">Email<input type="email" value={form.email} onChange={set("email")} /></label>
          <label className="field">Phone<input value={form.phone} onChange={set("phone")} /></label>
        </div>
        <div className="row">
          <label className="field">Address<input value={form.address} onChange={set("address")} /></label>
          <label className="field">Lead time (days)<input required type="number" min="0" step="1" value={form.lead_time_days} onChange={set("lead_time_days")} /></label>
        </div>
        <button className="primary" type="submit" disabled={saving}>{saving ? "Saving..." : editId ? "Save changes" : "Add supplier"}</button>{" "}
        {editId && <button type="button" className="small" onClick={reset}>Cancel</button>}
        {message.text && <p className={message.type}>{message.text}</p>}
      </form>

      <div className="panel">
        <h2>All suppliers</h2>
        <Status loading={suppliers.loading} error={suppliers.error} />
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>Company</th><th>Contact</th><th>Email</th><th>Phone</th><th>Address</th>
                <th className="right">Lead time</th><th></th>
              </tr>
            </thead>
            <tbody>
              {(suppliers.data || []).map((s) => (
                <tr key={s.id}>
                  <td>{s.name}</td><td>{s.contact_person || "-"}</td><td>{s.email || "-"}</td><td>{s.phone || "-"}</td>
                  <td>{s.address || "-"}</td>
                  <td className="right">{s.lead_time_days ?? "-"} d</td>
                  <td>
                    <button className="small" onClick={() => setSelected(s)}>View</button>
                    <button className="small" onClick={() => edit(s)}>Edit</button>
                    <button className="small" onClick={() => remove(s)}>Delete</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!suppliers.loading && (suppliers.data || []).length === 0 && <p className="muted">No suppliers yet.</p>}
      </div>

      {selected && (
        <div>
          <p>
            Showing details for <strong>{selected.name}</strong>{" "}
            <button type="button" className="small" onClick={() => setSelected(null)}>Close</button>
          </p>
          <div className="grid2">
            <div className="panel">
              <h2>Products from {selected.name}</h2>
              <Status loading={products.loading} error={products.error} />
              {products.data?.length === 0 && <p className="muted">No products linked to this supplier.</p>}
              <table>
                <thead><tr><th>Product</th><th>SKU</th><th className="right">In stock</th></tr></thead>
                <tbody>
                  {(products.data || []).map((p) => (
                    <tr key={p.id}><td>{p.name}</td><td>{p.sku}</td><td className="right">{p.current_stock}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>

            <div className="panel">
              <h2>Purchase history</h2>
              <Status loading={purchases.loading} error={purchases.error} />
              {purchases.data && (
                <p className="muted">
                  {purchases.data.purchase_count} purchase(s), total spent {money(purchases.data.total_spent)}
                </p>
              )}
              {purchases.data && history.length === 0 && <p className="muted">No purchases from this supplier yet.</p>}
              <div className="scroll">
                <table>
                  <thead>
                    <tr><th>Date</th><th>Product</th><th className="right">Qty</th><th className="right">Unit cost</th><th className="right">Total</th></tr>
                  </thead>
                  <tbody>
                    {history.map((t) => (
                      <tr key={t.purchase_id}>
                        <td>{when(t.purchase_date)}</td>
                        <td>{t.product_name}</td>
                        <td className="right">{t.quantity}</td>
                        <td className="right">{money(t.unit_cost)}</td>
                        <td className="right">{money(t.total_cost)}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}