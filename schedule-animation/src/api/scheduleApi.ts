import type { AnimationScheduleItem, ScheduleAnimationPageResponse } from '../types/schedule';
import { dedupeScheduleRows } from '../utils/dedupeScheduleRows';
import { parseScheduleAnimationPageJson } from '../utils/parseScheduleAnimationJson';
import { parseScheduleCsv } from '../utils/parseScheduleCsv';
import { parseScheduleXlsxToAnimation } from '../utils/parseScheduleXlsx';
import { applyStaffingRequirementsToItems } from '../utils/parseStaffingRequirementsXlsx';

const API_BASE_URL = import.meta.env.VITE_API_URL ?? '';

const DEFAULT_PAGE_SIZE = Number(import.meta.env.VITE_SCHEDULE_PAGE_SIZE) || 150;

function publicBaseUrl(): string {
    return import.meta.env.BASE_URL.endsWith('/') ? import.meta.env.BASE_URL : `${import.meta.env.BASE_URL}/`;
}

let staffingBufferMemo: ArrayBuffer | null | undefined;

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

/** Подмешивает норму из `public/staffing_requirements.xlsx`, если файл есть. */
export async function attachPublicStaffingRequirements(
    items: AnimationScheduleItem[],
): Promise<AnimationScheduleItem[]> {
    if (items.length === 0) return items;
    const buf = await loadPublicStaffingBufferOnce();
    if (!buf) return items;
    return applyStaffingRequirementsToItems(items, buf);
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
