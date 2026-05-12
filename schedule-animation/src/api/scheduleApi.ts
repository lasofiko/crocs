import type { AnimationScheduleItem, ScheduleAnimationPageResponse } from '../types/schedule';
import { dedupeScheduleRows } from '../utils/dedupeScheduleRows';
import { parseScheduleAnimationPageJson } from '../utils/parseScheduleAnimationJson';
import { parseScheduleCsv } from '../utils/parseScheduleCsv';
import { parseScheduleXlsxToAnimation } from '../utils/parseScheduleXlsx';
import {
    applyStaffingRequirementsToItems,
    parseStaffingRequirementsFull,
} from '../utils/parseStaffingRequirementsXlsx';
import { mergeForecastGuestsIntoItems, parseForecastGuestsByDateHour } from '../utils/parseForecastGuestsXlsx';

const API_BASE_URL = import.meta.env.VITE_API_URL ?? '';

const DEFAULT_PAGE_SIZE = Number(import.meta.env.VITE_SCHEDULE_PAGE_SIZE) || 150;

function publicBaseUrl(): string {
    return import.meta.env.BASE_URL.endsWith('/') ? import.meta.env.BASE_URL : `${import.meta.env.BASE_URL}/`;
}

let staffingBufferMemo: ArrayBuffer | null | undefined;
let forecastBufferMemo: ArrayBuffer | null | undefined;

async function loadPublicStaffingBufferOnce(): Promise<ArrayBuffer | null> {
    if (staffingBufferMemo !== undefined) {
        return staffingBufferMemo;
    }
    try {
        const res = await fetch(`${publicBaseUrl()}staffing_requirements.xlsx`);
        staffingBufferMemo = res.ok ? await res.arrayBuffer() : null;
    } catch {
        staffingBufferMemo = null;
    }
    return staffingBufferMemo;
}

async function loadPublicForecastBufferOnce(): Promise<ArrayBuffer | null> {
    if (forecastBufferMemo !== undefined) {
        return forecastBufferMemo;
    }
    try {
        const res = await fetch(`${publicBaseUrl()}forecast.xlsx`);
        forecastBufferMemo = res.ok ? await res.arrayBuffer() : null;
    } catch {
        forecastBufferMemo = null;
    }
    return forecastBufferMemo;
}

/** Если из Excel нет числа — стабильное «рандомное» по слоту дата|час (45…280). */
function fallbackVisitorsCount(seedKey: string): number {
    let h = 2_166_136_261;
    for (let i = 0; i < seedKey.length; i += 1) {
        h ^= seedKey.charCodeAt(i);
        h = Math.imul(h, 16_777_619);
    }
    return 45 + (Math.abs(h) % 236);
}

function ensureVisitorsOnItems(items: AnimationScheduleItem[]): AnimationScheduleItem[] {
    return items.map((it) => {
        if (it.visitorsCount !== undefined && Number.isFinite(it.visitorsCount) && it.visitorsCount > 0) {
            return it;
        }
        const key = `${it.date}|${it.hour}`;
        return { ...it, visitorsCount: fallbackVisitorsCount(key) };
    });
}

/** Посетители: приоритет `public/forecast.xlsx` (crocs: sale_date, sale_hour, guests_count), иначе колонка в staffing. */
export async function attachPublicVisitorsFromTables(
    items: AnimationScheduleItem[],
): Promise<AnimationScheduleItem[]> {
    if (items.length === 0) return items;

    let merged = items;

    const fBuf = await loadPublicForecastBufferOnce();
    if (fBuf) {
        const byHour = parseForecastGuestsByDateHour(fBuf);
        if (byHour.size > 0) {
            merged = mergeForecastGuestsIntoItems(items, fBuf);
        }
    }

    const sBuf = await loadPublicStaffingBufferOnce();
    if (sBuf) {
        const { explicitVisitorsByDateHour } = parseStaffingRequirementsFull(sBuf);
        if (explicitVisitorsByDateHour.size > 0) {
            merged = merged.map((it) => {
                const hasVisitors =
                    it.visitorsCount !== undefined &&
                    Number.isFinite(it.visitorsCount) &&
                    it.visitorsCount > 0;
                if (hasVisitors) return it;
                const v = explicitVisitorsByDateHour.get(`${it.date}|${it.hour}`);
                if (v !== undefined && v > 0) {
                    return { ...it, visitorsCount: v };
                }
                return it;
            });
        }
    }

    return ensureVisitorsOnItems(merged);
}

/** Нормы из staffing + посетители из forecast.xlsx или колонки в staffing. */
export async function attachPublicStaffingRequirements(
    items: AnimationScheduleItem[],
): Promise<AnimationScheduleItem[]> {
    if (items.length === 0) return items;
    const buf = await loadPublicStaffingBufferOnce();
    const withNorms = buf ? applyStaffingRequirementsToItems(items, buf) : items;
    return attachPublicVisitorsFromTables(withNorms);
}

/**
 * Расписание из `public/schedule.xlsx` (crocs: ds, station_key, employee_id, starttime, finishtime).
 * Если файла нет или он пустой — возвращает [].
 */
export async function tryLoadScheduleFromPublicXlsx(): Promise<AnimationScheduleItem[]> {
    try {
        const res = await fetch(`${publicBaseUrl()}schedule.xlsx`);
        if (!res.ok) return [];
        const buf = await res.arrayBuffer();
        const items = parseScheduleXlsxToAnimation(buf);
        return attachPublicStaffingRequirements(items);
    } catch {
        return [];
    }
}

export type FetchSchedulePageParams = {
    page?: number;
    pageSize?: number;
};

function scheduleListUrl(page: number, pageSize: number): string {
    const qs = new URLSearchParams({
        page: String(page),
        pageSize: String(pageSize),
        size: String(pageSize),
    });
    const path = `/api/schedule/animation?${qs.toString()}`;
    const base = API_BASE_URL.replace(/\/$/, '');
    if (!base) {
        return path;
    }
    return new URL(path, base.endsWith('/') ? base : `${base}/`).href;
}

/**
 * Порция расписания для анимации (JSON). Бэк может отдавать Spring Page или свой объект с items/hasMore.
 * Если приходит text/csv — парсится как раньше одной порцией (без пагинации на фронте).
 */
export async function fetchScheduleAnimationPage(
    params: FetchSchedulePageParams = {},
): Promise<ScheduleAnimationPageResponse> {
    const page = params.page ?? 0;
    const pageSize = params.pageSize ?? DEFAULT_PAGE_SIZE;

    const response = await fetch(scheduleListUrl(page, pageSize), {
        headers: { Accept: 'application/json, text/csv;q=0.9,*/*;q=0.8' },
    });

    if (!response.ok) {
        throw new Error(`Failed to fetch schedule page: ${response.status}`);
    }

    const contentType = response.headers.get('content-type') ?? '';
    const text = await response.text();

    if (
        contentType.includes('application/json') ||
        text.trimStart().startsWith('{') ||
        text.trimStart().startsWith('[')
    ) {
        try {
            const json: unknown = JSON.parse(text);
            return parseScheduleAnimationPageJson(json, page, pageSize);
        } catch {
            return {
                items: [],
                total: 0,
                page,
                pageSize,
                hasMore: false,
            };
        }
    }

    const csvItems = parseScheduleCsv(text);
    return {
        items: csvItems,
        total: csvItems.length,
        page,
        pageSize,
        hasMore: false,
    };
}

/** Загрузить всё расписание последовательными запросами (для простых сценариев). */
export async function fetchAnimationScheduleFull(): Promise<AnimationScheduleItem[]> {
    const merged: AnimationScheduleItem[] = [];
    let page = 0;

    while (true) {
        const chunk = await fetchScheduleAnimationPage({ page, pageSize: DEFAULT_PAGE_SIZE });
        merged.push(...chunk.items);

        if (!chunk.hasMore) {
            break;
        }

        page += 1;
    }

    return dedupeScheduleRows(merged);
}

/** @deprecated Используйте fetchScheduleAnimationPage или fetchAnimationScheduleFull */
export async function fetchAnimationSchedule(): Promise<AnimationScheduleItem[]> {
    return fetchAnimationScheduleFull();
}

export async function fetchScheduleExcel(): Promise<Blob> {
    const base = API_BASE_URL.replace(/\/$/, '');
    const path = '/api/schedule/excel';
    const url = base ? new URL(path, base.endsWith('/') ? base : `${base}/`).href : path;
    const response = await fetch(url);

    if (!response.ok) {
        throw new Error('Failed to fetch schedule excel');
    }

    return response.blob();
}

/** Скачать тот же файл, что лежит в `public/schedule.xlsx` (если есть). */
export async function fetchPublicScheduleXlsxBlob(): Promise<Blob> {
    const res = await fetch(`${publicBaseUrl()}schedule.xlsx`);
    if (!res.ok) {
        throw new Error('No public/schedule.xlsx');
    }
    return res.blob();
}

export { DEFAULT_PAGE_SIZE };
