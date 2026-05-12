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

function toRequiredInt(v: unknown): number | undefined {
    if (typeof v === 'number' && Number.isFinite(v)) {
        return Math.max(0, Math.round(v));
    }
    const n = parseInt(String(v).trim().replace(',', '.'), 10);
    if (Number.isFinite(n)) return Math.max(0, n);
    return undefined;
}

/** Ключ: `YYYY-MM-DD|hour|STATION` (станция в верхнем регистре). */
export function staffingRequirementLookupKey(dateIso: string, hour: number, station: string): string {
    return `${dateIso}|${hour}|${station.trim().toUpperCase()}`;
}

/**
 * Первый лист: дата/ds, час/hour, station_key, требуемое_число_работников (или близкие имена колонок).
 */
export function parseStaffingRequirementsMap(buffer: ArrayBuffer): Map<string, number> {
    const wb = XLSX.read(buffer, { type: 'array', cellDates: true });
    const name = wb.SheetNames[0];
    if (!name) return new Map();
    const sheet = wb.Sheets[name];
    const raw = XLSX.utils.sheet_to_json<Record<string, unknown>>(sheet, { defval: '' });
    const map = new Map<string, number>();

    for (const row of raw) {
        const ds = pick(row, ['ds', 'date', 'дата', 'day', 'sale_date']);
        const hourRaw = pick(row, ['hour', 'sale_hour', 'час', 'h']);
        const station = pick(row, ['station_key', 'station', 'станция']);
        const req = pick(row, [
            'требуемое_число_работников',
            'required_employees',
            'expected_people_count',
            'expectedpeoplecount',
            'ideal_staff',
            'norm',
        ]);

        if (ds === undefined || station === undefined) continue;
        const dateStr = toDateStr(ds);
        const hour = toHourInt(hourRaw);
        const required = toRequiredInt(req);
        if (hour === undefined || required === undefined) continue;

        const key = staffingRequirementLookupKey(dateStr, hour, String(station).trim());
        map.set(key, required);
    }

    return map;
}

/** Подставляет «норму» из staffing requirements; индикатор пустой — тон считает `staffingTone` по факту/норме. */
export function applyStaffingRequirementsToItems(
    items: AnimationScheduleItem[],
    staffingBuffer: ArrayBuffer,
): AnimationScheduleItem[] {
    const reqMap = parseStaffingRequirementsMap(staffingBuffer);
    if (reqMap.size === 0) return items;

    return items.map((item) => {
        const key = staffingRequirementLookupKey(item.date, item.hour, item.station);
        const required = reqMap.get(key);
        if (required === undefined) {
            return item;
        }
        const atStationCount =
            item.atStationCount !== undefined && Number.isFinite(item.atStationCount)
                ? item.atStationCount
                : item.employeeIds.length;
        return {
            ...item,
            expectedPeopleCount: required,
            expectationIndicator: '',
            atStationCount,
        };
    });
}
