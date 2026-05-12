import type { AnimationScheduleItem } from '../types/schedule';

export type WeekHourSlide = {
    day: number;
    hour: number;
    items: AnimationScheduleItem[];
};

/**
 * Слайды недели по порядку: понедельник 7:00 → … → воскресенье 23:00.
 * Для каждого слота — все станции из данных (или пустой список).
 */
export function buildWeekSlidesFromSchedule(allRows: AnimationScheduleItem[]): WeekHourSlide[] {
    const byKey = new Map<string, AnimationScheduleItem[]>();

    for (const row of allRows) {
        if (!Number.isFinite(row.day) || row.day < 1 || row.day > 7) {
            continue;
        }

        if (!Number.isFinite(row.hour) || row.hour < 0 || row.hour > 23) {
            continue;
        }

        const key = `${row.day}-${row.hour}`;
        const list = byKey.get(key);
        if (list) {
            list.push(row);
        } else {
            byKey.set(key, [row]);
        }
    }

    const slides: WeekHourSlide[] = [];

    for (let day = 1; day <= 7; day++) {
        const hourStart = day === 1 ? 7 : 0;
        for (let hour = hourStart; hour <= 23; hour++) {
            const key = `${day}-${hour}`;
            const items = byKey.get(key) ?? [];

            slides.push({ day, hour, items });
        }
    }

    return slides;
}
