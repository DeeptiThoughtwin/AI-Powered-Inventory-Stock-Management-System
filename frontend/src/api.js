const BASE = "http://127.0.0.1:8001";

export async function api(path, options = {}) {
  const res = await fetch(BASE + path, {
    headers: { "Content-Type": "application/json" },
    ...options,
    body: options.body ? JSON.stringify(options.body) : undefined,
  });
  let data = null;
  try {
    data = await res.json();
  } catch {
    data = null;
  }
  if (!res.ok) {
    let msg = "Request failed";
    if (data && typeof data.detail === "string") msg = data.detail;
    else if (data && Array.isArray(data.detail))
      msg = data.detail.map((d) => `${d.loc[d.loc.length - 1]}: ${d.msg}`).join(", ");
    throw new Error(msg);
  }
  return data;
}