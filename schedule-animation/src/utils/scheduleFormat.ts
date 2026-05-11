const DAYS = ['MON', 'TUE', 'WED', 'THU', 'FRI', 'SAT', 'SUN'];

export function formatHour(hour: number): string {
    return `${String(hour).padStart(2, '0')}:00`;
}

export function formatDay(day: number): string {
    return DAYS[day - 1] ?? 'MON';
}
