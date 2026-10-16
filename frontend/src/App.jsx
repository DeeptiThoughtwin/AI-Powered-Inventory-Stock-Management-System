import { useState } from "react";
import "./App.css";
import Dashboard from "./pages/Dashboard";
import Products from "./pages/Products";
import Suppliers from "./pages/Suppliers";
import Transactions from "./pages/Transactions";
import History from "./pages/History";
import Forecast from "./pages/Forecast";

const TABS = [
  ["dashboard", "Dashboard"],
  ["products", "Products"],
  ["suppliers", "Suppliers"],
  ["purchases", "Purchases"],
  ["sales", "Sales"],
  ["history", "Inventory history"],
  ["forecast", "Forecast & reorder"],
];

export default function App() {
  const [tab, setTab] = useState("dashboard");
  return (
    <div className="app">
      <div className="nav">
        {TABS.map(([id, label]) => (
          <button key={id} className={tab === id ? "active" : ""} onClick={() => setTab(id)}>
            {label}
          </button>
        ))}
      </div>
      {tab === "dashboard" && <Dashboard />}
      {tab === "products" && <Products />}
      {tab === "suppliers" && <Suppliers />}
      {tab === "purchases" && <Transactions key="purchase" kind="purchase" />}
      {tab === "sales" && <Transactions key="sale" kind="sale" />}
      {tab === "history" && <History />}
      {tab === "forecast" && <Forecast />}
    </div>
  );
}