import * as XLSX from 'xlsx';
import type { AnimationScheduleItem } from '../types/schedule';

type RawShift = {
    ds: string;
    station_key: string;
    employee_id: string;
    starttime: number;
    finishtime: number;
};

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

function toFloat(v: unknown): number {
    if (typeof v === 'number' && Number.isFinite(v)) return v;
    const n = parseFloat(String(v).trim().replace(',', '.'));
    return Number.isFinite(n) ? n : NaN;
}

function getDayFromDate(date: string): number {
    const weekDay = new Date(date).getDay();
    return weekDay === 0 ? 7 : weekDay;
}

function addDaysIso(iso: string, n: number): string {
    const [y, m, d] = iso.split('-').map(Number);
    const dt = new Date(y, m - 1, d + n);
    const yyyy = dt.getFullYear();
    const mm = String(dt.getMonth() + 1).padStart(2, '0');
    const dd = String(dt.getDate()).padStart(2, '0');
    return `${yyyy}-${mm}-${dd}`;
}

function parseIso(iso: string): number {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(y, m - 1, d).getTime();
}

/** Слот [h, h+1) пересекается с интервалом смены [start, fin) */
function slotIntersectsShift(hourInt: number, start: number, fin: number): boolean {
    const slot0 = hourInt;
    const slot1 = hourInt + 1;
    return Math.max(slot0, start) < Math.min(slot1, fin);
}

function readRawShifts(buffer: ArrayBuffer): RawShift[] {
    const wb = XLSX.read(buffer, { type: 'array', cellDates: true });
    const name = wb.SheetNames[0];
    if (!name) return [];
    const sheet = wb.Sheets[name];
    const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
    const out: RawShift[] = [];

    for (const row of raw) {
        const ds = pick(row, ['ds', 'date', 'day', 'sale_date']);
        const station = pick(row, ['station_key', 'station', 'станция']);
        const emp = pick(row, ['employee_id', 'employee', 'сотрудник', 'id']);
        const st = pick(row, ['starttime', 'start', 'from', 'начало']);
        const fin = pick(row, ['finishtime', 'finish', 'end', 'to', 'конец']);

        if (ds === undefined || station === undefined || emp === undefined) continue;
        const starttime = toFloat(st);
        const finishtime = toFloat(fin);
        if (!Number.isFinite(starttime) || !Number.isFinite(finishtime) || finishtime <= starttime) continue;

        out.push({
            ds: toDateStr(ds),
            station_key: String(station).trim(),
            employee_id: String(emp).trim(),
            starttime,
            finishtime,
        });
    }

    return out;
}

/**
 * Crocs-формат: ds, station_key, employee_id, starttime, finishtime (часы float).
 * Берётся первая календарная неделя по данным (от минимальной ds 7 дней), часы раскладываются по слотам для анимации.
 */
export function parseScheduleXlsxToAnimation(buffer: ArrayBuffer): AnimationScheduleItem[] {
    const shifts = readRawShifts(buffer);
    if (shifts.length === 0) return [];

    const uniqueDays = [...new Set(shifts.map((s) => s.ds))].sort((a, b) => parseIso(a) - parseIso(b));
    const weekStart = uniqueDays[0]!;
    const weekEnd = addDaysIso(weekStart, 6);

    const inWeek = shifts.filter((s) => s.ds >= weekStart && s.ds <= weekEnd);

    type Agg = { date: string; day: number; hour: number; station: string; ids: Set<string> };
    const acc = new Map<string, Agg>();

    for (const row of inWeek) {
        const day = getDayFromDate(row.ds);
        if (day < 1 || day > 7) continue;

        for (let hour = 0; hour < 24; hour += 1) {
            if (!slotIntersectsShift(hour, row.starttime, row.finishtime)) continue;
            const key = `${row.ds}|${day}|${hour}|${row.station_key}`;
            let g = acc.get(key);
            if (!g) {
                g = { date: row.ds, day, hour, station: row.station_key, ids: new Set() };
                acc.set(key, g);
            }
            g.ids.add(row.employee_id);
        }
    }

    const items: AnimationScheduleItem[] = [];
    for (const g of acc.values()) {
        const employeeIds = [...g.ids].sort();
        const atStationCount = employeeIds.length;
        items.push({
            date: g.date,
            hour: g.hour,
            station: g.station,
            employeeIds,
            expectedPeopleCount: Math.max(1, atStationCount),
            expectationIndicator: '',
            day: g.day,
            atStationCount,
        });
    }

    return items.sort((a, b) => {
        if (a.day !== b.day) return a.day - b.day;
        if (a.hour !== b.hour) return a.hour - b.hour;
        return a.station.localeCompare(b.station, 'ru');
    });
}
