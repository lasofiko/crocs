/** Индексы первой строки каждого уникального (день, час) в расписании. */
export function buildHourBoundaryIndices(schedule: { day: number; hour: number }[]): number[] {
    if (schedule.length === 0) {
        return [];
    }

    const boundaries: number[] = [];
    let lastKey = '';

    for (let i = 0; i < schedule.length; i++) {
        const key = `${schedule[i].day}-${schedule[i].hour}`;
        if (key !== lastKey) {
            boundaries.push(i);
            lastKey = key;
        }
    }

    return boundaries;
}

export function currentHourSegment(boundaries: number[], currentIndex: number): number {
    if (boundaries.length === 0) {
        return 0;
    }

    let segment = 0;
    for (let i = 0; i < boundaries.length; i++) {
        if (boundaries[i] <= currentIndex) {
            segment = i;
        } else {
            break;
        }
    }

    return segment;
}

export function nextHourStartIndex(boundaries: number[], currentIndex: number): number {
    if (boundaries.length === 0) {
        return 0;
    }

    const seg = currentHourSegment(boundaries, currentIndex);
    const nextSeg = (seg + 1) % boundaries.length;

    return boundaries[nextSeg];
}

export function prevHourStartIndex(boundaries: number[], currentIndex: number): number {
    if (boundaries.length === 0) {
        return 0;
    }

    const seg = currentHourSegment(boundaries, currentIndex);
    const prevSeg = (seg - 1 + boundaries.length) % boundaries.length;

    return boundaries[prevSeg];
}
