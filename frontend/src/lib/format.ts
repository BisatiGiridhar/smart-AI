export const fmt = (v: number | null | undefined, digits = 3) => (v === null || v === undefined || Number.isNaN(v) ? "—" : v.toFixed(digits));
export const pct = (v: number | null | undefined) => (v === null || v === undefined ? "—" : `${Math.round(v * 100)}%`);
export const when = (iso?: string | null) => (iso ? new Date(iso).toLocaleString() : "—");
export const short = (id?: string | null) => (id ? id.slice(0, 8) : "—");
export const ci = (c?: [number, number] | number[] | null, d = 3) => (c && c.length === 2 ? `[${c[0].toFixed(d)}, ${c[1].toFixed(d)}]` : "n/a");
