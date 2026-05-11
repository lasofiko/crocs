import type { AnimationScheduleItem } from '../types/schedule';
import { parseScheduleCsv } from '../utils/parseScheduleCsv';

const API_BASE_URL = import.meta.env.VITE_API_URL ?? '';

export async function fetchAnimationSchedule(): Promise<AnimationScheduleItem[]> {
    const response = await fetch(`${API_BASE_URL}/api/schedule/animation`);

    if (!response.ok) {
        throw new Error('Failed to fetch animation schedule');
    }

    return parseScheduleCsv(await response.text());
}

export async function fetchScheduleExcel(): Promise<Blob> {
    const response = await fetch(`${API_BASE_URL}/api/schedule/excel`);

    if (!response.ok) {
        throw new Error('Failed to fetch schedule excel');
    }

    return response.blob();
}
