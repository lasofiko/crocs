import * as XLSX from 'xlsx';
import type { AnimationScheduleItem } from '../types/schedule';

function normKey(k: string): string {
    return String(k).trim().toLowerCase().replace(/\s+/g, '_');
}

function pick(row: Record<string, unknown>, keys: string[]): unknown {
    const map = new Map<string, unknown>();
    for (const [k, v] of Object.entries(row)) {
        map.set(normKey(k), v);
    }
    for (const key of keys) {
        const v = map.get(normKey(key));
        if (v !== undefined && v !== null && v !== '') return v;
    }
    return undefined;
}

function toDateStr(v: unknown): string {
    if (v instanceof Date && !Number.isNaN(v.getTime())) {
        return v.toISOString().slice(0, 10);
    }
    if (typeof v === 'number' && v > 1_000) {
        const ms = Math.round((v - 25_569) * 86_400 * 1000);
        const d = new Date(ms);
        if (!Number.isNaN(d.getTime())) return d.toISOString().slice(0, 10);
    }
    const s = String(v).trim();
    if (/^\d{4}-\d{2}-\d{2}/.test(s)) return s.slice(0, 10);
    return s.slice(0, 10);
}

function toHourInt(v: unknown): number | undefined {
    if (typeof v === 'number' && Number.isFinite(v)) {
        const h = Math.trunc(v);
        return h >= 0 && h <= 23 ? h : undefined;
    }
    const n = parseInt(String(v).trim(), 10);
    if (Number.isFinite(n) && n >= 0 && n <= 23) return n;
    return undefined;
}

function toGuestsInt(v: unknown): number | undefined {
    if (typeof v === 'number' && Number.isFinite(v) && v >= 0) {
        return Math.round(v);
    }
    const n = parseFloat(String(v).trim().replace(',', '.'));
    if (Number.isFinite(n) && n >= 0) return Math.round(n);
    return undefined;
}

/** Ключ как в staffing: `YYYY-MM-DD|hour` */
function dateHourKey(dateIso: string, hour: number): string {
    return `${dateIso}|${hour}`;
}

/**
 * Crocs `forecast.xlsx`: sale_date, sale_hour, guests_count (или ds / guests).
 * Несколько строк на один час — берём максимум guests_count.
 */
export function parseForecastGuestsByDateHour(buffer: ArrayBuffer): Map<string, number> {
    const wb = XLSX.read(buffer, { type: 'array', cellDates: true });
    const name = wb.SheetNames[0];
    const map = new Map<string, number>();
    if (!name) return map;

    const sheet = wb.Sheets[name];
    const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });

    for (const row of raw) {
        const ds = pick(row, ['sale_date', 'ds', 'date', 'дата']);
        const hourRaw = pick(row, ['sale_hour', 'hour', 'час']);
        const g = pick(row, ['guests_count', 'guests', 'посетители', 'visitors_count']);
        if (ds === undefined) continue;
        const dateStr = toDateStr(ds);
        const hour = toHourInt(hourRaw);
        const guests = toGuestsInt(g);
        if (hour === undefined || guests === undefined || guests < 0) continue;
        const k = dateHourKey(dateStr, hour);
        map.set(k, Math.max(map.get(k) ?? 0, guests));
    }

    return map;
}

export function mergeForecastGuestsIntoItems(
    items: AnimationScheduleItem[],
    forecastBuffer: ArrayBuffer,
): AnimationScheduleItem[] {
    const byHour = parseForecastGuestsByDateHour(forecastBuffer);
    if (byHour.size === 0) return items;

    return items.map((it) => {
        const k = dateHourKey(it.date, it.hour);
        const v = byHour.get(k);
        if (v === undefined || v <= 0) return it;
        return { ...it, visitorsCount: v };
    });
}
