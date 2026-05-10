export type AnimationScheduleItem = {
    date: string;
    hour: number;
    station: string;
    employeeIds: string[];
    expectedPeopleCount: number;
    expectationIndicator: string;
    day: number;
};
