export type StaffingTone = 'ok' | 'warn' | 'bad';

/** Индикатор выполнения нормы по числу людей на точке */
export function staffingTone(
    expected: number,
    atStation: number,
    expectationIndicator: string,
): StaffingTone {
    const raw = expectationIndicator.trim().toLowerCase();
    if (raw === 'ok' || raw === 'good' || raw === 'green' || raw === 'норма') return 'ok';
    if (raw === 'warn' || raw === 'warning' || raw === 'yellow' || raw === 'внимание') return 'warn';
    if (raw === 'bad' || raw === 'red' || raw === 'critical' || raw === 'критично') return 'bad';

    if (expected <= 0) {
        return atStation > 0 ? 'ok' : 'warn';
    }

    if (atStation >= expected) return 'ok';
    if (atStation >= expected - 1 || atStation / expected >= 0.75) return 'warn';
    return 'bad';
}
