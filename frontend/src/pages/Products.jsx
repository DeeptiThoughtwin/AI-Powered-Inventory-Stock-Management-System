import { useState } from "react";
import { api } from "../api";
import { useApi } from "../hooks";
import { Status, money } from "../ui";

const EP = { list: "/products?include_inactive=true", create: "/products", update: (id) => `/products/${id}` };
const EMPTY = { sku: "", name: "", category: "", purchase_price: "", selling_price: "", current_stock: "0", minimum_stock: "0", supplier_id: "" };

export default function Products() {
  const products = useApi(EP.list);
  const suppliers = useApi("/suppliers");
  const [form, setForm] = useState(EMPTY);
  const [editId, setEditId] = useState(null);
  const [search, setSearch] = useState("");
  const [message, setMessage] = useState({ type: "", text: "" });
  const [saving, setSaving] = useState(false);

  const set = (k) => (e) => setForm({ ...form, [k]: e.target.value });
  const supplierName = (id) => (suppliers.data || []).find((s) => s.id === id)?.name || "-";

  function edit(p) {
    setEditId(p.id);
    setForm({
      sku: p.sku, name: p.name, category: p.category || "",
      purchase_price: String(p.purchase_price), selling_price: String(p.selling_price),
      current_stock: String(p.current_stock), minimum_stock: String(p.minimum_stock),
      supplier_id: p.supplier_id ? String(p.supplier_id) : "",
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

    const body = {
      sku: form.sku.trim(),
      name: form.name.trim(),
      category: form.category.trim() || null,
      purchase_price: Number(form.purchase_price),
      selling_price: Number(form.selling_price),
      minimum_stock: Number(form.minimum_stock),
      supplier_id: form.supplier_id ? Number(form.supplier_id) : null,
      current_stock: Number(form.current_stock),
    };

    try {
      if (editId) {
        // The backend saves the details and, if the stock changed,
        // writes the stock history row itself. No second request needed.
        await api(EP.update(editId), { method: "PUT", body });
        setMessage({ type: "ok", text: "Product updated successfully." });
      } else {
        await api(EP.create, { method: "POST", body });
        setMessage({ type: "ok", text: "Product created successfully." });
      }

      reset();
      products.reload();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    } finally {
      setSaving(false);
    }
  }

  async function toggleActive(p) {
    try {
      await api(`/products/${p.id}/${p.is_active === false ? "activate" : "deactivate"}`, { method: "PATCH" });
      products.reload();
    } catch (err) {
      setMessage({ type: "error", text: err.message });
    }
  }

  const rows = (products.data || []).filter((p) => {
    const t = search.toLowerCase();
    return !t || p.name.toLowerCase().includes(t) || p.sku.toLowerCase().includes(t) || (p.category || "").toLowerCase().includes(t);
  });

  function badge(p) {
    if (p.is_active === false) return <span className="badge gray">Inactive</span>;
    if (p.current_stock <= 0) return <span className="badge red">Out of stock</span>;
    if (p.current_stock <= p.minimum_stock) return <span className="badge amber">Low stock</span>;
    return <span className="badge green">Available</span>;
  }

  return (
    <div>
      <h1>Products</h1>

      <form className="panel" onSubmit={submit}>
        <h2>{editId ? "Edit product" : "Add product"}</h2>
        <div className="row">
          <label className="field">SKU<input required value={form.sku} onChange={set("sku")} /></label>
          <label className="field">Name<input required value={form.name} onChange={set("name")} /></label>
          <label className="field">Category<input value={form.category} onChange={set("category")} /></label>
          <label className="field">Supplier
            <select value={form.supplier_id} onChange={set("supplier_id")}>
              <option value="">No supplier</option>
              {(suppliers.data || []).map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
        </div>
        <div className="row">
          <label className="field">Purchase cost<input required type="number" min="0" step="0.01" value={form.purchase_price} onChange={set("purchase_price")} /></label>
          <label className="field">Selling price<input required type="number" min="0" step="0.01" value={form.selling_price} onChange={set("selling_price")} /></label>

          {/* In stock input box now shows whether adding or editing */}
          <label className="field">
            {editId ? "In stock" : "Opening stock"}
            <input required type="number" min="0" step="1" value={form.current_stock} onChange={set("current_stock")} />
          </label>

          <label className="field">Minimum stock<input required type="number" min="0" step="1" value={form.minimum_stock} onChange={set("minimum_stock")} /></label>
        </div>
        <button className="primary" type="submit" disabled={saving}>{saving ? "Saving..." : editId ? "Save changes" : "Add product"}</button>{" "}
        {editId && <button type="button" className="small" onClick={reset}>Cancel</button>}
        {message.text && <p className={message.type}>{message.text}</p>}
      </form>

      <div className="panel">
        <h2>All products</h2>
        <div className="row">
          <label className="field">Search
            <input placeholder="Name, SKU or category" value={search} onChange={(e) => setSearch(e.target.value)} />
          </label>
        </div>
        <Status loading={products.loading} error={products.error} />
        <div className="scroll">
          <table>
            <thead>
              <tr>
                <th>SKU</th><th>Name</th><th>Category</th><th>Supplier</th>
                <th className="right">Cost</th><th className="right">Price</th>
                <th className="right">In stock</th><th className="right">Min</th>
                <th className="right">Stock value</th><th>Status</th><th></th>
              </tr>
            </thead>
            <tbody>
              {rows.map((p) => (
                <tr key={p.id}>
                  <td>{p.sku}</td><td>{p.name}</td><td>{p.category || "-"}</td><td>{supplierName(p.supplier_id)}</td>
                  <td className="right">{money(p.purchase_price)}</td>
                  <td className="right">{money(p.selling_price)}</td>
                  <td className="right">{p.current_stock}</td>
                  <td className="right">{p.minimum_stock}</td>
                  <td className="right">{money(p.current_stock * p.purchase_price)}</td>
                  <td>{badge(p)}</td>
                  <td>
                    <button className="small" onClick={() => edit(p)}>Edit</button>
                    <button className="small" onClick={() => toggleActive(p)}>{p.is_active === false ? "Activate" : "Deactivate"}</button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        {!products.loading && rows.length === 0 && <p className="muted">No products found.</p>}
      </div>
    </div>
  );
}