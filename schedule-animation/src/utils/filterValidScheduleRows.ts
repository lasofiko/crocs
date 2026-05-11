import type { AnimationScheduleItem } from '../types/schedule';

/** Отсекаем ответы вроде index.html, попавшие в CSV-парсер. */
export function filterValidScheduleRows(items: AnimationScheduleItem[]): AnimationScheduleItem[] {
    return items.filter((item) => {
        if (!Number.isFinite(item.hour) || item.hour < 0 || item.hour > 23) {
            return false;
        }

        if (!Number.isFinite(item.day) || item.day < 1 || item.day > 7) {
            return false;
        }

        if (!item.station?.trim()) {
            return false;
        }

        return true;
    });
}
