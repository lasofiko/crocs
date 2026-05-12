import type { AnimationScheduleItem } from '../types/schedule';

type StationCode = 'K' | 'FF' | 'BVR' | 'C' | 'TS';

const POOL: Record<StationCode, string[]> = {
    K: ['E-1101', 'E-1102', 'E-1103'],
    FF: ['E-2201', 'E-2202'],
    BVR: ['E-3301', 'E-3302'],
    C: ['E-4401', 'E-4402', 'E-4403'],
    TS: ['E-5501', 'E-5502', 'E-5503', 'E-5504'],
};

function staffForSlot(station: StationCode, day: number, hour: number): string[] {
    const pool = POOL[station];
    const seed = (day * 31 + hour * 7 + station.charCodeAt(0)) % 9;
    const want = 1 + (seed % pool.length);
    return pool.slice(0, want);
}

function expectedFor(station: StationCode, hour: number): number {
    const base: Record<StationCode, number> = {
        K: 3,
        FF: 2,
        BVR: 2,
        C: 3,
        TS: 4,
    };
    const bump = hour >= 12 && hour <= 14 ? 1 : 0;
    return base[station] + bump;
}

function indicatorFor(expected: number, actual: number): string {
    if (actual >= expected) return '';
    if (actual >= expected - 1) return 'warn';
    return 'bad';
}

/** Демо-строки: пн–вс, каждый час 7–23, все станции — чтобы таймлайн и карточки были заполнены */
export function buildMockScheduleAnimationRows(): AnimationScheduleItem[] {
    const stations: StationCode[] = ['K', 'FF', 'BVR', 'C', 'TS'];
    const rows: AnimationScheduleItem[] = [];

    for (let day = 1; day <= 7; day++) {
        const hourStart = day === 1 ? 7 : 0;
        for (let hour = hourStart; hour <= 23; hour++) {
            const visitorsCount = 55 + day * 6 + (hour - 7) * 4 + (hour >= 12 && hour <= 15 ? 35 : 0);

            for (const station of stations) {
                const employeeIds = staffForSlot(station, day, hour);
                const expectedPeopleCount = expectedFor(station, hour);
                const atStationCount = employeeIds.length;
                rows.push({
                    date: '2026-05-12',
                    hour,
                    station,
                    employeeIds,
                    expectedPeopleCount,
                    expectationIndicator: indicatorFor(expectedPeopleCount, atStationCount),
                    day,
                    visitorsCount,
                    atStationCount,
                });
            }
        }
    }

    return rows;
}

export const MOCK_SCHEDULE_ANIMATION_ROWS: AnimationScheduleItem[] = buildMockScheduleAnimationRows();
