export type AnimationScheduleItem = {
    date: string;
    hour: number;
    station: string;
    employeeIds: string[];
    /** Оптимально необходимое число работников на точке (норма) */
    expectedPeopleCount: number;
    expectationIndicator: string;
    day: number;
    /** Посетители в этот день/час (если бэк отдаёт на каждой строке — обычно одинаковое для всех точек часа) */
    visitorsCount?: number;
    /** Фактически людей на точке в этой ситуации */
    atStationCount?: number;
};

/** Ответ порционной выдачи расписания для анимации */
export type ScheduleAnimationPageResponse = {
    items: AnimationScheduleItem[];
    total: number;
    page: number;
    pageSize: number;
    hasMore: boolean;
};
