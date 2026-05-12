import type { AnimationScheduleItem } from '../types/schedule';

/** Сливаем порции: одна строка на пару (день, час, станция) — побеждает последняя версия. */
export function dedupeScheduleRows(rows: AnimationScheduleItem[]): AnimationScheduleItem[] {
    const map = new Map<string, AnimationScheduleItem>();

    for (const row of rows) {
        map.set(`${row.day}-${row.hour}-${row.station}`, row);
    }

    return Array.from(map.values()).sort((a, b) => {
        if (a.day !== b.day) return a.day - b.day;
        if (a.hour !== b.hour) return a.hour - b.hour;
        return a.station.localeCompare(b.station, 'ru');
    });
}
