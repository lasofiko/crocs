import type { AnimationScheduleItem, ScheduleAnimationPageResponse } from '../types/schedule';

function pick(row: Record<string, unknown>, keys: string[]): unknown {
    for (const key of keys) {
        if (key in row && row[key] !== undefined && row[key] !== null && row[key] !== '') {
            return row[key];
        }
    }

    return undefined;
}

function toNum(value: unknown): number {
    const n = Number(value);
    return Number.isFinite(n) ? n : NaN;
}

function toStr(value: unknown): string {
    return value == null ? '' : String(value).trim();
}

function dayFromDate(date: string): number {
    const weekDay = new Date(date).getDay();
    return weekDay === 0 ? 7 : weekDay;
}

function parseEmployeeIds(value: unknown): string[] {
    if (Array.isArray(value)) {
        return value.map((v) => String(v).trim()).filter(Boolean);
    }

    if (typeof value === 'string') {
        return value
            .split(/[;,|]/)
            .map((s) => s.trim())
            .filter(Boolean);
    }

    return [];
}

function asRecord(value: unknown): Record<string, unknown> | null {
    return value !== null && typeof value === 'object' && !Array.isArray(value)
        ? (value as Record<string, unknown>)
        : null;
}

/** Одна строка ответа бэка → модель UI */
export function mapJsonRowToScheduleItem(row: Record<string, unknown>): AnimationScheduleItem {
    const date = toStr(pick(row, ['date', 'ds', 'workDate']));

    const dayRaw = pick(row, ['day', 'weekday', 'weekDay', 'dow']);
    const day = toNum(dayRaw) || (date ? dayFromDate(date) : NaN);

    const hour = toNum(pick(row, ['hour', 'sale_hour', 'hourOfDay']));

    const station = toStr(pick(row, ['station', 'station_key', 'stationKey', 'point', 'stationName']));

    const employeeIds = parseEmployeeIds(pick(row, ['employeeIds', 'employee_ids', 'employees', 'workers', 'workerIds']));

    const expectedPeopleCount = toNum(
        pick(row, [
            'expectedPeopleCount',
            'requiredWorkers',
            'optimalWorkers',
            'required_workers',
            'optimal_staff',
            'staff_required',
        ]),
    );

    const atStationCount = toNum(
        pick(row, ['atStationCount', 'peopleAtStation', 'scheduled_count', 'actual_workers', 'workers_at_station']),
    );

    const visitorsCount = toNum(pick(row, ['visitorsCount', 'visitors', 'guests_count', 'guestsCount']));

    const expectationIndicator = toStr(pick(row, ['expectationIndicator', 'expectation_indicator', 'status', 'indicator']));

    return {
        date,
        hour,
        station,
        employeeIds,
        expectedPeopleCount: Number.isFinite(expectedPeopleCount) ? expectedPeopleCount : 0,
        expectationIndicator,
        day: Number.isFinite(day) && day >= 1 && day <= 7 ? day : 1,
        visitorsCount: Number.isFinite(visitorsCount) ? visitorsCount : undefined,
        atStationCount: Number.isFinite(atStationCount) ? atStationCount : undefined,
    };
}

function parseItemsArray(raw: unknown): AnimationScheduleItem[] {
    if (!Array.isArray(raw)) {
        return [];
    }

    return raw.map((entry) => mapJsonRowToScheduleItem(asRecord(entry) ?? {}));
}

/**
 * Разбор тела ответа порционной ручки.
 * Поддержка: { items, total, page, pageSize, hasMore }, Spring Page { content, totalElements, number, size, last },
 * обёртка { data: ... }, либо просто массив строк.
 */
export function parseScheduleAnimationPageJson(json: unknown, fallbackPage: number, fallbackPageSize: number): ScheduleAnimationPageResponse {
    const root = asRecord(json) ?? {};
    const wrapped = asRecord(root.data) ?? asRecord(root.result) ?? root;

    let itemsRaw: unknown = wrapped.items ?? wrapped.content ?? wrapped.records ?? wrapped.rows;

    if (Array.isArray(json)) {
        itemsRaw = json;
    }

    const items = parseItemsArray(itemsRaw ?? []);

    const total = toNum(wrapped.total ?? wrapped.totalElements ?? wrapped.total_count) || items.length;
    const page = toNum(wrapped.page ?? wrapped.number ?? wrapped.pageNumber);
    const pageSize = toNum(wrapped.pageSize ?? wrapped.size ?? wrapped.limit) || fallbackPageSize;

    const pageNorm = Number.isFinite(page) ? page : fallbackPage;
    const pageSizeNorm = Number.isFinite(pageSize) ? pageSize : fallbackPageSize;

    let hasMore: boolean | undefined;

    if (typeof wrapped.hasMore === 'boolean') {
        hasMore = wrapped.hasMore;
    } else if (typeof wrapped.last === 'boolean') {
        hasMore = !wrapped.last;
    } else if (typeof wrapped.has_next === 'boolean') {
        hasMore = wrapped.has_next;
    }

    if (hasMore === undefined) {
        if (items.length === 0) {
            hasMore = false;
        } else if (items.length < pageSizeNorm) {
            hasMore = false;
        } else {
            hasMore = pageNorm * pageSizeNorm + items.length < total;
        }
    }

    return {
        items,
        total: Number.isFinite(total) ? total : items.length,
        page: pageNorm,
        pageSize: pageSizeNorm,
        hasMore,
    };
}
