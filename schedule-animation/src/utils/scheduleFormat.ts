const DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];

/** Короткие подписи дней недели (пн … вс) */
export const WEEKDAY_SHORT_RU = ['ПН', 'ВТ', 'СР', 'ЧТ', 'ПТ', 'СБ', 'ВС'] as const;

export function formatHour(hour: number): string {
    return `${String(hour).padStart(2, '0')}:00`;
}

export function formatDay(day: number): string {
    return DAYS[day - 1] ?? 'MON';
}

export function weekdayShortRu(day: number): string {
    return WEEKDAY_SHORT_RU[day - 1] ?? 'ПН';
}
